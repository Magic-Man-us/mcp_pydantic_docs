"""
Source-based documentation extraction from Git repositories.

Replaces HTML-based extraction with direct extraction from source repositories
to eliminate formatting artifacts (line numbers, table cruft, navigation elements).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Literal, Optional

import git
import tiktoken
from pydantic import BaseModel, Field

from .logger import logger

# ============================================================================
# Pydantic Models
# ============================================================================


class DocumentChunk(BaseModel):
    """Represents a documentation chunk for indexing."""

    title: str = Field(description="Section or symbol title")
    anchor: Optional[str] = Field(
        None, description="HTML anchor/fragment identifier"
    )
    heading_level: int = Field(
        0, description="Heading level (0 for non-heading content)"
    )
    md_text: str = Field(description="Clean markdown/plaintext content")
    url: str = Field(description="Canonical URL for this content")
    page: str = Field(description="Relative page path")
    source_site: Literal["pydantic", "pydantic_ai"] = Field(
        description="Source project"
    )

    def to_jsonl(self) -> dict:
        """Convert to JSONL-compatible dict format."""
        return {
            "title": self.title,
            "anchor": self.anchor,
            "heading_level": self.heading_level,
            "md_text": self.md_text,
            "url": self.url,
            "page": self.page,
            "source_site": self.source_site,
        }


class PythonSymbolDoc(BaseModel):
    """Documentation extracted from Python source."""

    symbol_name: str = Field(
        description="Fully qualified symbol name (e.g., pydantic.BaseModel)"
    )
    symbol_type: Literal["class", "function", "method", "module"] = Field(
        description="Type of Python symbol"
    )
    docstring: str = Field(description="Raw docstring content")
    source_file: Path = Field(
        description="Source file path relative to repo root"
    )
    line_number: int = Field(description="Line number where symbol is defined")
    parent_class: Optional[str] = Field(
        None, description="Parent class name for methods"
    )


class RepoConfig(BaseModel):
    """Configuration for a documentation repository."""

    name: Literal["pydantic", "pydantic_ai"]
    repo_url: str = Field(description="GitHub repository URL")
    branch: str = Field(default="main", description="Git branch to clone")
    docs_path: Path = Field(
        description="Path to markdown docs within repo (e.g., docs/)"
    )
    source_path: Path = Field(
        description="Path to Python source within repo (e.g., pydantic/)"
    )
    base_url: str = Field(description="Base URL for documentation site")


# ============================================================================
# Repository Configurations
# ============================================================================

PYDANTIC_CONFIG = RepoConfig(
    name="pydantic",
    repo_url="https://github.com/pydantic/pydantic.git",
    branch="main",
    docs_path=Path("docs"),
    source_path=Path("pydantic"),
    base_url="https://docs.pydantic.dev/latest",
)

PYDANTIC_AI_CONFIG = RepoConfig(
    name="pydantic_ai",
    repo_url="https://github.com/pydantic/pydantic-ai.git",
    branch="main",
    docs_path=Path("docs"),
    source_path=Path("pydantic_ai_slim"),
    base_url="https://ai.pydantic.dev",
)


# ============================================================================
# Repository Management
# ============================================================================


def clone_or_update_repo(config: RepoConfig, target_dir: Path) -> Path:
    """
    Clone or pull repository to local directory.

    Args:
        config: Repository configuration
        target_dir: Local directory for cloned repo

    Returns:
        Path to cloned repository

    Raises:
        git.GitCommandError: If git operations fail
    """
    repo_path = target_dir / config.name
    
    try:
        if repo_path.exists() and (repo_path / ".git").exists():
            logger.info(f"Updating existing repository: {config.name}")
            repo = git.Repo(repo_path)
            origin = repo.remotes.origin
            origin.pull(config.branch)
            logger.info(f"Repository updated: {config.name}")
        else:
            logger.info(f"Cloning repository: {config.name}")
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            git.Repo.clone_from(
                config.repo_url, repo_path, branch=config.branch, depth=1
            )
            logger.info(f"Repository cloned: {config.name}")
        
        return repo_path
    except git.GitCommandError as e:
        logger.error(f"Git operation failed for {config.name}: {e}")
        raise


# ============================================================================
# Text Processing Utilities
# ============================================================================


def clean_docstring(docstring: str) -> str:
    """
    Clean and normalize a Python docstring.

    Removes markdown admonitions (!!!, ???), normalizes whitespace,
    but preserves code blocks and meaningful formatting.

    Args:
        docstring: Raw docstring text

    Returns:
        Cleaned docstring text
    """
    if not docstring:
        return ""
    
    # Remove markdown admonitions (!!!, ???, etc.)
    lines = []
    skip_admonition = False
    
    for line in docstring.split("\n"):
        stripped = line.strip()
        
        # Check for admonition start
        if stripped.startswith(("!!!", "???")):
            skip_admonition = True
            continue
        
        # Check if we're still in admonition (indented content)
        if skip_admonition:
            if stripped and not line.startswith(("    ", "\t")):
                skip_admonition = False
            else:
                continue
        
        lines.append(line)
    
    cleaned = "\n".join(lines)
    
    # Normalize excessive whitespace but preserve intentional spacing
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    
    return cleaned.strip()


def chunk_text(text: str, max_tokens: int = 1200) -> list[str]:
    """
    Split long text into token-aware chunks.

    Args:
        text: Text to chunk
        max_tokens: Maximum tokens per chunk

    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)
        
        if len(tokens) <= max_tokens:
            return [text]
        
        # Split by paragraphs first
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            para_tokens = len(encoding.encode(para))
            
            if current_tokens + para_tokens > max_tokens and current_chunk:
                # Save current chunk
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens
        
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        return chunks
    except Exception as e:
        logger.warning(f"Token-based chunking failed: {e}, using simple split")
        # Fallback to character-based chunking
        max_chars = max_tokens * 4  # Rough estimate
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def build_api_url(symbol_name: str, base_url: str) -> str:
    """
    Build API reference URL for a Python symbol.

    Args:
        symbol_name: Fully qualified symbol name
        base_url: Base documentation URL

    Returns:
        Full URL to API documentation
    """
    # For pydantic: https://docs.pydantic.dev/latest/api/base_model/
    # For pydantic-ai: https://ai.pydantic.dev/api/agent/
    
    parts = symbol_name.split(".")
    if len(parts) < 2:
        return f"{base_url}/api/"
    
    module = parts[1] if len(parts) > 1 else parts[0]
    
    # Convert to URL-friendly format
    url_part = module.lower().replace("_", "-")
    
    return f"{base_url}/api/{url_part}/"


# ============================================================================
# Markdown Extraction
# ============================================================================


def extract_heading_info(line: str) -> tuple[int, str, str]:
    """
    Extract heading level, text, and anchor from a markdown heading.

    Args:
        line: Markdown line

    Returns:
        Tuple of (level, text, anchor)
    """
    match = re.match(r"^(#{1,6})\s+(.+)$", line)
    if not match:
        return 0, "", ""
    
    level = len(match.group(1))
    text = match.group(2).strip()
    
    # Generate anchor from text
    anchor = text.lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    anchor = re.sub(r"[-\s]+", "-", anchor)
    
    return level, text, anchor


def process_markdown_file(
    file_path: Path,
    repo_path: Path,
    base_url: str,
    source_site: Literal["pydantic", "pydantic_ai"],
) -> list[DocumentChunk]:
    """
    Process a single markdown file into chunks.

    Args:
        file_path: Path to markdown file
        repo_path: Repository root path
        base_url: Base URL for building full URLs
        source_site: Source identifier

    Returns:
        List of document chunks
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return []
    
    # Build relative page path
    rel_path = file_path.relative_to(repo_path)
    page_path = str(rel_path).replace(".md", "").replace("index", "")
    
    # Build URL
    if page_path:
        url = f"{base_url}/{page_path.rstrip('/')}/"
    else:
        url = f"{base_url}/"
    
    chunks = []
    current_section = []
    current_heading = ""
    current_level = 0
    current_anchor = None
    
    for line in content.split("\n"):
        level, heading_text, anchor = extract_heading_info(line)
        
        if level > 0:
            # Save previous section
            if current_section:
                section_text = "\n".join(current_section).strip()
                if section_text:
                    for text_chunk in chunk_text(section_text):
                        chunks.append(
                            DocumentChunk(
                                title=current_heading or file_path.stem,
                                anchor=current_anchor,
                                heading_level=current_level,
                                md_text=text_chunk,
                                url=url if not current_anchor else f"{url}#{current_anchor}",
                                page=page_path,
                                source_site=source_site,
                            )
                        )
            
            # Start new section
            current_heading = heading_text
            current_level = level
            current_anchor = anchor
            current_section = []
        else:
            current_section.append(line)
    
    # Save final section
    if current_section:
        section_text = "\n".join(current_section).strip()
        if section_text:
            for text_chunk in chunk_text(section_text):
                chunks.append(
                    DocumentChunk(
                        title=current_heading or file_path.stem,
                        anchor=current_anchor,
                        heading_level=current_level,
                        md_text=text_chunk,
                        url=url if not current_anchor else f"{url}#{current_anchor}",
                        page=page_path,
                        source_site=source_site,
                    )
                )
    
    return chunks


def extract_markdown_docs(
    repo_path: Path,
    docs_path: Path,
    base_url: str,
    source_site: Literal["pydantic", "pydantic_ai"],
) -> list[DocumentChunk]:
    """
    Extract documentation from markdown files in docs/ folder.

    Args:
        repo_path: Path to cloned repository root
        docs_path: Relative path to docs folder (e.g., docs/)
        base_url: Base URL for building full URLs
        source_site: Source site identifier

    Returns:
        List of document chunks from markdown files
    """
    full_docs_path = repo_path / docs_path
    
    if not full_docs_path.exists():
        logger.warning(f"Docs path not found: {full_docs_path}")
        return []
    
    chunks = []
    
    # Find all markdown files
    md_files = list(full_docs_path.rglob("*.md"))
    logger.info(f"Found {len(md_files)} markdown files in {source_site}")
    
    for md_file in md_files:
        file_chunks = process_markdown_file(
            md_file, repo_path, base_url, source_site
        )
        chunks.extend(file_chunks)
        logger.debug(f"Extracted {len(file_chunks)} chunks from {md_file.name}")
    
    logger.info(f"Extracted {len(chunks)} total chunks from markdown docs")
    return chunks


# ============================================================================
# Python Docstring Extraction
# ============================================================================


def parse_python_file(file_path: Path) -> list[PythonSymbolDoc]:
    """
    Parse a Python file and extract all documented symbols.

    Args:
        file_path: Path to Python source file

    Returns:
        List of symbol documentation objects
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
        return []
    
    symbols = []
    
    for node in ast.walk(tree):
        # Only process nodes that can have docstrings
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
            
        docstring = ast.get_docstring(node)
        if not docstring:
            continue
        
        symbol_name: Optional[str] = None
        symbol_type: Optional[Literal["class", "function", "method", "module"]] = None
        parent_class: Optional[str] = None
        line_num = 0
        
        if isinstance(node, ast.Module):
            symbol_name = file_path.stem
            symbol_type = "module"
            line_num = 1
        elif isinstance(node, ast.ClassDef):
            symbol_name = node.name
            symbol_type = "class"
            line_num = node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check if it's a method (inside a class)
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef) and node in parent.body:
                    symbol_name = f"{parent.name}.{node.name}"
                    symbol_type = "method"
                    parent_class = parent.name
                    break
            
            if not symbol_name:
                symbol_name = node.name
                symbol_type = "function"
            line_num = node.lineno
        
        if symbol_name and symbol_type:
            symbols.append(
                PythonSymbolDoc(
                    symbol_name=symbol_name,
                    symbol_type=symbol_type,
                    docstring=docstring,
                    source_file=file_path,
                    line_number=line_num,
                    parent_class=parent_class,
                )
            )
    
    return symbols


def extract_python_docstrings(
    repo_path: Path,
    source_path: Path,
    base_url: str,
    source_site: Literal["pydantic", "pydantic_ai"],
) -> list[DocumentChunk]:
    """
    Extract API documentation from Python source docstrings.

    Uses AST parsing to extract clean docstrings from classes, functions,
    and methods. Builds proper URLs pointing to API reference pages.

    Args:
        repo_path: Path to cloned repository root
        source_path: Relative path to source code (e.g., pydantic/)
        base_url: Base URL for API documentation
        source_site: Source site identifier

    Returns:
        List of document chunks from Python docstrings
    """
    full_source_path = repo_path / source_path
    
    if not full_source_path.exists():
        logger.warning(f"Source path not found: {full_source_path}")
        return []
    
    chunks = []
    
    # Find all Python files
    py_files = list(full_source_path.rglob("*.py"))
    logger.info(f"Found {len(py_files)} Python files in {source_site}")
    
    for py_file in py_files:
        symbols = parse_python_file(py_file)
        
        for symbol in symbols:
            cleaned_doc = clean_docstring(symbol.docstring)
            if not cleaned_doc:
                continue
            
            # Build URL for this symbol
            url = build_api_url(symbol.symbol_name, base_url)
            
            # Build page path
            rel_path = py_file.relative_to(repo_path)
            page_path = str(rel_path).replace(".py", "")
            
            # Create chunks from docstring
            for text_chunk in chunk_text(cleaned_doc):
                chunks.append(
                    DocumentChunk(
                        title=symbol.symbol_name,
                        anchor=symbol.symbol_name.lower().replace(".", "-"),
                        heading_level=0,
                        md_text=text_chunk,
                        url=url,
                        page=page_path,
                        source_site=source_site,
                    )
                )
        
        if symbols:
            logger.debug(
                f"Extracted {len(symbols)} symbols from {py_file.name}"
            )
    
    logger.info(
        f"Extracted {len(chunks)} total chunks from Python docstrings"
    )
    return chunks


# ============================================================================
# Main Extraction Pipeline
# ============================================================================


def process_site(
    config: RepoConfig, target_dir: Path, output_file: Path
) -> int:
    """
    Process a complete documentation site.

    Args:
        config: Repository configuration
        target_dir: Directory for cloning repos
        output_file: Output JSONL file path

    Returns:
        Number of chunks extracted
    """
    logger.info(f"Processing {config.name} documentation")
    
    # Clone or update repository
    repo_path = clone_or_update_repo(config, target_dir)
    
    # Extract from markdown docs
    md_chunks = extract_markdown_docs(
        repo_path, config.docs_path, config.base_url, config.name
    )
    
    # Extract from Python docstrings
    py_chunks = extract_python_docstrings(
        repo_path, config.source_path, config.base_url, config.name
    )
    
    # Combine all chunks
    all_chunks = md_chunks + py_chunks
    logger.info(f"Total chunks for {config.name}: {len(all_chunks)}")
    
    # Write to JSONL
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with output_file.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk.to_jsonl()) + "\n")
    
    logger.info(f"Wrote {len(all_chunks)} chunks to {output_file}")
    return len(all_chunks)


def main() -> bool:
    """
    Main extraction function.

    Returns:
        True if extraction succeeded, False otherwise
    """
    try:
        # Set up paths
        project_root = Path(__file__).parent.parent
        target_dir = project_root / "docs_raw"
        data_dir = project_root / "data"
        
        # Process Pydantic
        pydantic_count = process_site(
            PYDANTIC_CONFIG,
            target_dir,
            data_dir / "pydantic.jsonl",
        )
        
        # Process Pydantic AI
        pydantic_ai_count = process_site(
            PYDANTIC_AI_CONFIG,
            target_dir,
            data_dir / "pydantic_ai.jsonl",
        )
        
        logger.info(
            f"Extraction complete: {pydantic_count + pydantic_ai_count} total chunks"
        )
        return True
    
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    main()

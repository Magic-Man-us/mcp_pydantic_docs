from __future__ import annotations

import json
import pathlib
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

import tiktoken
from bs4 import BeautifulSoup
from bs4.element import Tag
from markdownify import markdownify as md

from mcp_pydantic_docs.logger import logger
from mcp_pydantic_docs.mcp import bs4_has_lxml

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_DIRS = [
    ROOT/"docs_raw/pydantic",
    ROOT/"docs_raw/pydantic_ai",
    ROOT/"docs_raw/pydantic_settings"
]
MD_DIR   = ROOT/"docs_md"
DATA_DIR = ROOT/"data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MD_DIR.mkdir(parents=True, exist_ok=True)

enc = tiktoken.get_encoding("cl100k_base")
MAX_TOK = 1200  # target chunk size

_MAIN_SELECTORS = [
    "main[role='main']",
    "main",
    "div.md-content__inner",
    "div.md-content",
    "div.md-main__inner",
    "article",
    "div.md-typeset",
]
_REMOVE_SELECTORS = [
    "nav",
    "header",
    "footer",
    "aside",
    ".md-header",
    ".md-sidebar",
    ".md-nav",
    ".md-footer",
    ".md-search",
    ".md-search__overlay",
    ".md-tabs",
    ".skip-link",
    ".sr-only",
    ".visually-hidden",
    "script",
    "style",
]


def _clean_html_for_text(html: str) -> str:
    """Remove navigation, headers, footers, and extract main content."""
    soup = BeautifulSoup(html, "lxml" if bs4_has_lxml() else "html.parser")

    # Remove obvious boilerplate anywhere
    for sel in _REMOVE_SELECTORS:
        for el in soup.select(sel):
            el.decompose()

    # Prefer main content container
    main = None
    for sel in _MAIN_SELECTORS:
        main = soup.select_one(sel)
        if main:
            break

    # If we found a main container, use only that
    if isinstance(main, Tag):
        return str(main)

    # Otherwise return the cleaned full document
    return str(soup)


def _normalize_text(text: str) -> str:
    """Aggressively normalize text to remove excessive whitespace and newlines."""
    if not text:
        return ""

    # Strip leading/trailing whitespace first
    text = text.strip()

    # Remove carriage returns and other control characters
    text = text.replace("\r", "")
    text = text.replace("\x00", "")
    
    # Remove common markdown artifacts that create empty sections
    text = re.sub(r"^\s*[#]+\s*$", "", text, flags=re.MULTILINE)  # Empty headings
    text = re.sub(r"^\s*[-*_]+\s*$", "", text, flags=re.MULTILINE)  # Empty dividers
    text = re.sub(r"^\s*>\s*$", "", text, flags=re.MULTILINE)  # Empty quotes
    
    # Aggressively collapse any sequence of 2+ newlines to exactly 2
    # This handles cases with hundreds of consecutive newlines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    
    # Clean up each line: collapse multiple spaces to single space
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # Strip leading/trailing whitespace from each line
        line = line.strip()
        # Collapse multiple spaces to single space
        line = re.sub(r"\s+", " ", line)
        # Only keep non-empty lines or intentional blank lines (for paragraph breaks)
        if line or (cleaned_lines and cleaned_lines[-1]):
            cleaned_lines.append(line)
    
    text = "\n".join(cleaned_lines)
    
    # Final aggressive pass: no more than 2 consecutive newlines anywhere
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    
    # Remove leading/trailing whitespace again
    text = text.strip()
    
    # Remove any remaining excessive whitespace patterns
    text = re.sub(r"[ \t]+\n", "\n", text)  # Trailing spaces before newlines
    text = re.sub(r"\n[ \t]+", "\n", text)  # Leading spaces after newlines
    
    return text


def _html_to_markdown(clean_html: str) -> str:
    """Convert cleaned HTML to markdown with aggressive normalization."""
    soup = BeautifulSoup(clean_html, "lxml" if bs4_has_lxml() else "html.parser")

    # Remove any remaining navigation or boilerplate elements
    for tag in soup.find_all(['nav', 'aside', 'header', 'footer']):
        tag.decompose()
    
    # Remove empty tags that create unnecessary whitespace
    for tag in soup.find_all():
        if not tag.get_text(strip=True) and tag.name not in ['br', 'hr', 'img']:
            tag.decompose()

    # Mark code blocks for preservation
    for pre in soup.find_all("pre"):
        pre["data-preserve"] = "1"

    # Convert to markdown with specific options to reduce whitespace
    md_text = md(
        str(soup),
        heading_style="ATX",
        strip=['script', 'style'],
        escape_asterisks=False,
        escape_underscores=False,
    )

    # Remove empty code blocks
    md_text = re.sub(r"```\s*\n\s*```", "", md_text)
    
    # Remove excessive blank lines created by markdown conversion
    md_text = re.sub(r"\n{3,}", "\n\n", md_text)
    
    # Clean up markdown list items with excessive newlines
    md_text = re.sub(r"(\n[-*+]\s+[^\n]+)\n{2,}(?=\n[-*+]\s+)", r"\1\n", md_text)
    
    # Apply aggressive text normalization
    md_text = _normalize_text(md_text)

    return md_text


def split_by_sections(md_text: str, base_url: str) -> list[dict[str, Any]]:
    """Split markdown into sections by H2/H3 headings with token-aware chunking."""
    lines = md_text.splitlines()
    chunks = []
    current = {"title": None, "anchor": None, "body": []}

    def push() -> None:
        if current["title"] and current["body"]:
            body = "\n".join(current["body"]).strip()
            # Token-aware sub-chunking
            toks = enc.encode(body)
            if len(toks) <= MAX_TOK:
                chunks.append(
                    {
                        "title": current["title"],
                        "anchor": current["anchor"],
                        "md_text": body,
                    }
                )
            else:
                # Split on paragraphs to fit token budget
                paras = body.split("\n\n")
                acc = []
                count = 0
                for p in paras:
                    ct = len(enc.encode(p))
                    if count + ct > MAX_TOK and acc:
                        chunks.append(
                            {
                                "title": current["title"],
                                "anchor": current["anchor"],
                                "md_text": "\n\n".join(acc),
                            }
                        )
                        acc, count = [], 0
                    acc.append(p)
                    count += ct
                if acc:
                    chunks.append(
                        {
                            "title": current["title"],
                            "anchor": current["anchor"],
                            "md_text": "\n\n".join(acc),
                        }
                    )

    for ln in lines:
        if ln.startswith("## "):  # H2
            push()
            title = ln.lstrip("#").strip()
            anchor = re.sub(r"[^a-z0-9\- ]", "", title.lower()).replace(" ", "-")
            current = {"title": title, "anchor": anchor, "body": []}
        elif ln.startswith("### "):  # H3
            push()
            title = ln.lstrip("#").strip()
            anchor = re.sub(r"[^a-z0-9\- ]", "", title.lower()).replace(" ", "-")
            current = {"title": title, "anchor": anchor, "body": []}
        else:
            current["body"].append(ln)
    push()

    # Attach URLs
    for c in chunks:
        c["url"] = base_url + (f"#{c['anchor']}" if c["anchor"] else "")
    return chunks


def _process_single_file(
    args: tuple[pathlib.Path, pathlib.Path, str, str],
) -> list[dict[str, Any]]:
    """Process a single HTML file and return records."""
    html_path, raw_root, base_url, site_name = args

    rel = html_path.relative_to(raw_root).as_posix()
    url = base_url.rstrip("/") + "/" + rel
    html = html_path.read_text(encoding="utf-8", errors="ignore")

    clean_html = _clean_html_for_text(html)
    md_text = _html_to_markdown(clean_html)
    sects = split_by_sections(md_text, url)

    # Write page-level markdown
    page_md_path = MD_DIR / (site_name + "-" + rel.replace("/", "_") + ".md")
    page_md_path.parent.mkdir(parents=True, exist_ok=True)
    page_md_path.write_text(md_text, encoding="utf-8")

    records = []
    for s in sects:
        s["page"] = rel
        s["source_site"] = site_name
        records.append(s)

    return records


def process_site(
    raw_root: pathlib.Path,
    base_url: str,
    out_jsonl: pathlib.Path,
    max_workers: int | None = None,
) -> None:
    """Process all HTML files in raw_root and write extracted sections to JSONL.

    Args:
        raw_root: Root directory containing HTML files
        base_url: Base URL for the documentation site
        out_jsonl: Output JSONL file path
        max_workers: Maximum number of worker processes (default: min(CPU count, 4))
    """
    import os

    # Use 50% of available CPU cores to keep system responsive
    if max_workers is None:
        cpu_count = os.cpu_count() or 1
        max_workers = max(2, cpu_count // 2)  # At least 2, at most 50% of cores
    html_files = list(raw_root.rglob("*.html"))
    if not html_files:
        logger.warning(f"No HTML files found in {raw_root}")
        return

    logger.info(f"Processing {len(html_files)} HTML files from {raw_root.name}...")

    # Prepare arguments for parallel processing
    args_list = [
        (html_path, raw_root, base_url, raw_root.name) for html_path in html_files
    ]

    all_records = []

    # Process files in parallel
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_single_file, args): args[0] for args in args_list
        }

        completed = 0
        for future in as_completed(futures):
            try:
                records = future.result()
                all_records.extend(records)
                completed += 1
                if completed % 10 == 0 or completed == len(html_files):
                    logger.info(f"  Processed {completed}/{len(html_files)} files...")
            except Exception as e:
                html_path = futures[future]
                logger.error(f"Error processing {html_path}: {e}")

    # Write all records to JSONL
    logger.info(f"Writing {len(all_records)} records to {out_jsonl.name}")
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info(f"✓ Completed {raw_root.name}: {len(all_records)} records")


def main() -> None:
    """Main entry point for extracting docs to JSONL with parallel processing."""
    import time

    start = time.time()

    logger.info("=" * 60)
    logger.info("NORMALIZING DOCUMENTATION TO JSONL")
    logger.info("=" * 60)

    process_site(RAW_DIRS[0], "https://docs.pydantic.dev/latest", DATA_DIR/"pydantic.jsonl")
    process_site(RAW_DIRS[1], "https://ai.pydantic.dev", DATA_DIR/"pydantic_ai.jsonl")
    if RAW_DIRS[2].exists():
        process_site(RAW_DIRS[2], "https://docs.pydantic.dev/latest/concepts/pydantic_settings", DATA_DIR/"pydantic_settings.jsonl")

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info(f"✓ Normalization complete in {elapsed:.1f}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

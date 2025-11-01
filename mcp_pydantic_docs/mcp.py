# src/mcp_pydantic_docs/mcp.py
from __future__ import annotations

import json
import logging
import os
import pathlib
import pickle
import re
import sys
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationError

# ---- mode ----
# Dynamic offline mode: starts permissive, locks offline after docs are cached
_OFFLINE_ONLY = True  # Will be dynamically adjusted based on cache state

# ---- logging ----
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- paths & constants (env-overrideable) ----
def _find_project_root() -> pathlib.Path:
    """
    Find the project root directory intelligently.
    Works in both development and installed modes.
    """
    # Start from this file's location
    current = pathlib.Path(__file__).resolve().parent
    
    # Look for data directory by walking up the tree
    for parent in [current] + list(current.parents):
        data_dir = parent / "data"
        docs_raw = parent / "docs_raw"
        
        # Check if this looks like our project root
        if data_dir.exists() or docs_raw.exists():
            return parent
        
        # Also check one level down (in case we're in the package dir)
        if (parent / "mcp_pydantic_docs" / "data").exists():
            return parent / "mcp_pydantic_docs"
    
    # Fallback to parent of parent (legacy behavior)
    return pathlib.Path(__file__).resolve().parents[1]

PKG_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = _find_project_root()

DOC_ROOT = pathlib.Path(
    os.getenv("PDA_DOC_ROOT", PROJECT_ROOT / "docs_raw" / "pydantic")
).resolve()
DOC_ROOT_AI = pathlib.Path(
    os.getenv("PDA_DOC_ROOT_AI", PROJECT_ROOT / "docs_raw" / "pydantic_ai")
).resolve()
DATA_DIR = pathlib.Path(os.getenv("PDA_DATA_DIR", PROJECT_ROOT / "data")).resolve()

BASE_PYDANTIC = "https://docs.pydantic.dev/latest/"
BASE_PYDANTIC_AI = "https://ai.pydantic.dev/"

BM25_PATH = DATA_DIR / "pydantic_all_bm25.pkl"
RECORDS_PATH = DATA_DIR / "pydantic_all_records.pkl"
_HAS_BM25 = BM25_PATH.exists() and RECORDS_PATH.exists()

INDEX_PATH = DOC_ROOT / "search" / "search_index.json"
MAX_SNIPPET = 800
MAX_SECTION = 4000

LOCAL_BASE_P = "local://pydantic/"
LOCAL_BASE_AI = "local://pydantic-ai/"

# ---- schemas ----
class SearchHit(BaseModel):
    title: str
    url: str
    anchor: Optional[str] = None
    snippet: str = Field(default="", max_length=1200)
    heading_title: Optional[str] = None  # new


class SearchResponse(BaseModel):
    results: List[SearchHit]

class GetResponse(BaseModel):
    url: str
    path: str
    text: str
    html: str
    truncated: bool = False
    text_length: int = 0
    html_length: int = 0
    max_chars: Optional[int] = None

class SectionResponse(BaseModel):
    url: str
    path: str
    anchor: str
    section: str
    truncated: bool = False

def _extract_headings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml" if bs4_has_lxml() else "html.parser")
    out: list[dict] = []
    for h in soup.select("h1[id],h2[id],h3[id]"):
        out.append({"anchor": h.get("id"), "title": h.get_text(" ", strip=True)})
    return out


@lru_cache(maxsize=1)
def _mkdocs_load_index() -> Dict[str, Any]:
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    docs: List[Dict[str, Any]] = []
    for html_path in DOC_ROOT.rglob("*.html"):
        try:
            raw = html_path.read_text(encoding="utf-8", errors="ignore")
            soup = BeautifulSoup(raw, "lxml" if bs4_has_lxml() else "html.parser")
            text = soup.get_text(" ")
            rel = html_path.relative_to(DOC_ROOT).as_posix()
            docs.append(
                {
                    "location": rel,
                    "title": html_path.stem,
                    "text": text,
                    "headings": _extract_headings(raw),
                }
            )
        except Exception:
            continue
    return {"docs": docs}
# ---- helpers ----
def bs4_has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except Exception:
        return False

def _is_within(root: pathlib.Path, path: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False

def _deny_remote(s: str) -> None:
    if not _OFFLINE_ONLY:
        return
    u = urlparse(s)
    if u.scheme in {"http", "https"}:
        # allow only known bases as identifiers; still read from local disk
        if not (s.startswith(BASE_PYDANTIC) or s.startswith(BASE_PYDANTIC_AI)):
            raise ValueError("Remote URLs disabled. Use local path or allowed doc base URL.")

def _safe_rel_from_url(path_or_url: str) -> Tuple[pathlib.Path, str]:
    s = path_or_url.strip()
    _deny_remote(s)
    if s.startswith(BASE_PYDANTIC):
        root, rel = DOC_ROOT, s[len(BASE_PYDANTIC):]
    elif s.startswith(BASE_PYDANTIC_AI):
        root, rel = DOC_ROOT_AI, s[len(BASE_PYDANTIC_AI):]
    elif s.startswith(LOCAL_BASE_P):
        root, rel = DOC_ROOT, s[len(LOCAL_BASE_P) :]
    elif s.startswith(LOCAL_BASE_AI):
        root, rel = DOC_ROOT_AI, s[len(LOCAL_BASE_AI) :]
    else:
        # For relative paths, try pydantic_ai first, then pydantic
        rel_clean = s.split("#", 1)[0].lstrip("/").replace("..", "")
        ai_path = (DOC_ROOT_AI / rel_clean).resolve()
        p_path = (DOC_ROOT / rel_clean).resolve()

        if ai_path.is_file() and _is_within(DOC_ROOT_AI, ai_path):
            root, rel = DOC_ROOT_AI, s
        elif p_path.is_file() and _is_within(DOC_ROOT, p_path):
            root, rel = DOC_ROOT, s
        else:
            # Default to pydantic for backward compatibility
            root, rel = DOC_ROOT, s
    rel = rel.split("#", 1)[0]
    rel = rel.lstrip("/").replace("..", "")
    return root, rel

def _display_url(root: pathlib.Path, rel: str) -> str:
    return (LOCAL_BASE_P if root == DOC_ROOT else LOCAL_BASE_AI) + rel

def _read_page(root: pathlib.Path, rel: str) -> str:
    rel = rel.lstrip("/").replace("..", "")
    path = (root / rel).resolve()
    if not path.is_file() or not _is_within(root, path):
        raise FileNotFoundError(rel)
    return path.read_text(encoding="utf-8", errors="ignore")

def _extract_section(html_str: str, anchor: str) -> str:
    soup = BeautifulSoup(html_str, "lxml" if bs4_has_lxml() else "html.parser")
    target = soup.find(id=anchor) or soup.select_one(f"h1#{anchor},h2#{anchor},h3#{anchor}")
    if not isinstance(target, Tag):
        return ""
    level = 2
    if isinstance(target.name, str) and target.name.startswith("h") and target.name[1:].isdigit():
        level = int(target.name[1:])
    out: List[str] = [target.get_text(" ", strip=True)]
    for sib in target.find_all_next():
        if not isinstance(sib, Tag):
            continue
        if isinstance(sib.name, str) and re.fullmatch(r"h[1-6]", sib.name) and int(sib.name[1]) <= level:
            break
        out.append(sib.get_text(" ", strip=True))
    text = "\n".join(filter(None, out))
    return text[:MAX_SECTION]


@lru_cache(maxsize=1)
def _load_bm25() -> Tuple[Any, Any]:
    with BM25_PATH.open("rb") as f1, RECORDS_PATH.open("rb") as f2:
        bm25 = pickle.load(f1)
        records = pickle.load(f2)
    return bm25, records


INDEX = None if _HAS_BM25 else _mkdocs_load_index()


# --- snippet cleaning ---
_SNIP_MAX = 420
_LINE_NO_BURST = re.compile(r"(?:^|\s)(?:\d{1,4}\s+){5,}\d{1,4}(?=\s|$)")
_FENCE = re.compile(r"`{3,}.*?`{3,}", re.S)  # strip fenced blocks
_PIPE_ROWS = re.compile(r"^\s*\|.*\|\s*$", re.M)  # drop markdown table rows
_MULTI_WS = re.compile(r"\s+")


def _clean_snippet(s: str) -> str:
    """Clean snippet for search results."""
    # drop obvious noise first
    s = _FENCE.sub(" ", s)
    s = _PIPE_ROWS.sub(" ", s)
    s = _LINE_NO_BURST.sub(" ", s)
    # collapse pipes & leftover fence ticks
    s = s.replace("|", " ").replace("`", " ")
    # collapse whitespace and trim
    s = _MULTI_WS.sub(" ", s).strip()
    # bound length
    return s[:_SNIP_MAX]


def _tokenize(s: str) -> List[str]:
    s = s.lower()
    s = re.sub(r"[^a-z0-9_#\-\s]", " ", s)
    return [t for t in s.split() if len(t) > 1]


def _rank_hits_bm25(query: str, k: int = 10) -> List[Dict[str, Any]]:
    bm25, records = _load_bm25()
    toks = _tokenize(query)
    scores = bm25.get_scores(toks)
    idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    out: List[Dict[str, Any]] = []
    q = " ".join(toks)
    for i in idxs:
        r = records[i]
        text = r.get("md_text") or ""
        pos = text.lower().find(q) if q else -1
        raw = text[max(0, pos - 120) : pos + 200] if pos != -1 else text[:MAX_SNIPPET]
        snippet = _clean_snippet(raw)
        out.append(
            {
                "title": r.get("title", ""),
                "url": _display_url(
                    DOC_ROOT_AI if r.get("source_site") == "pydantic_ai" else DOC_ROOT,
                    r.get("page", ""),
                ),
                "anchor": r.get("anchor"),
                "snippet": snippet,
                "page": r.get("page"),
                "source_site": r.get("source_site"),
            }
        )
    return out


def _rank_hits_mkdocs(query: str, k: int = 10) -> List[Dict[str, Any]]:
    q = query.lower()
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for d in INDEX.get("docs", []):  # type: ignore[union-attr]
        text = d.get("text", "")
        tl = text.lower()
        title = d.get("title", "").lower()
        score = 3 * title.count(q) + tl.count(q)
        if score:
            scored.append((score, d))
    scored.sort(reverse=True, key=lambda x: x[0])
    out: List[Dict[str, Any]] = []
    for _, d in scored[:k]:
        rel = d["location"]
        base_root = DOC_ROOT_AI if (DOC_ROOT_AI.exists() and (DOC_ROOT_AI / rel).exists()) else DOC_ROOT
        text = d.get("text", "")
        tl = text.lower()
        pos = tl.find(q)
        raw = (
            text[max(0, pos - 120) : pos + 200].replace("\n", " ")
            if pos != -1
            else text[:MAX_SNIPPET]
        )
        snippet = _clean_snippet(raw)
        out.append(
            {
                "title": d.get("title", ""),
                "url": _display_url(base_root, rel),
                "anchor": None,
                "snippet": snippet,
            }
        )
    return out

# ---- Startup validation and auto-initialization ----
def _validate_indices() -> tuple[bool, str]:
    """Validate that search indices exist and are loadable."""
    if not BM25_PATH.exists() or not RECORDS_PATH.exists():
        return False, "Search indices not found."
    try:
        _load_bm25()
        return True, "Search indices loaded successfully"
    except Exception as e:
        return False, f"Failed to load indices: {e}"

def _auto_initialize() -> None:
    """
    Automatically initialize search indices if missing.
    Called on server startup to ensure the server is ready to use.
    """
    # Check if indices already exist
    if BM25_PATH.exists() and RECORDS_PATH.exists():
        logger.info("Search indices found, server ready")
        return
    
    logger.info("Search indices not found, initializing...")
    
    # Check if data directory exists
    if not DATA_DIR.exists():
        logger.error("=" * 80)
        logger.error("DATA DIRECTORY NOT FOUND")
        logger.error(f"Expected location: {DATA_DIR}")
        logger.error("")
        logger.error("This usually means:")
        logger.error("  1. The repository was not cloned correctly")
        logger.error("  2. The path configuration is wrong")
        logger.error("")
        logger.error("Solutions:")
        logger.error("  - Ensure you cloned the complete git repository")
        logger.error("  - Check that data/*.jsonl files are present")
        logger.error("  - Or download fresh data:")
        logger.error("    uv run python -m mcp_pydantic_docs.setup --download --build-index")
        logger.error("=" * 80)
        return
    
    # Check if JSONL source files exist
    pydantic_jsonl = DATA_DIR / "pydantic.jsonl"
    pydantic_ai_jsonl = DATA_DIR / "pydantic_ai.jsonl"
    
    missing_files = []
    if not pydantic_jsonl.exists():
        missing_files.append(str(pydantic_jsonl))
    if not pydantic_ai_jsonl.exists():
        missing_files.append(str(pydantic_ai_jsonl))
    
    if missing_files:
        logger.error("=" * 80)
        logger.error("REQUIRED DATA FILES NOT FOUND")
        logger.error("")
        logger.error("Missing files:")
        for f in missing_files:
            logger.error(f"  - {f}")
        logger.error("")
        logger.error("These JSONL files should be included in the git repository.")
        logger.error("")
        logger.error("Solutions:")
        logger.error("  1. If you just cloned: Try 'git pull' to ensure you have all files")
        logger.error("  2. Check .gitignore doesn't exclude data/*.jsonl")
        logger.error("  3. Download and build fresh data:")
        logger.error("     uv run python -m mcp_pydantic_docs.setup --download --build-index")
        logger.error("")
        logger.error("Note: The JSONL files (~6MB) should be in the repository.")
        logger.error("      If missing, the git clone may be incomplete.")
        logger.error("=" * 80)
        return
    
    # Build indices from JSONL files
    try:
        logger.info("Building search indices from JSONL files...")
        logger.info(f"  Source: {pydantic_jsonl.name} ({pydantic_jsonl.stat().st_size / 1024 / 1024:.1f}MB)")
        logger.info(f"  Source: {pydantic_ai_jsonl.name} ({pydantic_ai_jsonl.stat().st_size / 1024 / 1024:.1f}MB)")
        
        from mcp_pydantic_docs.indexer import build_index
        
        jsonl_files = [pydantic_jsonl, pydantic_ai_jsonl]
        
        # Check for optional pydantic_settings
        settings_jsonl = DATA_DIR / "pydantic_settings.jsonl"
        if settings_jsonl.exists():
            jsonl_files.append(settings_jsonl)
            logger.info(f"  Source: {settings_jsonl.name} ({settings_jsonl.stat().st_size / 1024 / 1024:.1f}MB)")
        
        build_index(jsonl_files, "pydantic_all")
        
        logger.info("")
        logger.info("✓ Search indices built successfully")
        logger.info(f"  BM25 index: {BM25_PATH.stat().st_size / 1024 / 1024:.1f}MB")
        logger.info(f"  Records: {RECORDS_PATH.stat().st_size / 1024 / 1024:.1f}MB")
        logger.info("  Server is ready!")
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error("FAILED TO BUILD SEARCH INDICES")
        logger.error(f"Error: {e}")
        logger.error("")
        logger.error("The server will continue but search functionality will be limited.")
        logger.error("")
        logger.error("To fix:")
        logger.error("  uv run python -m mcp_pydantic_docs.indexer")
        logger.error("=" * 80)

# ---- MCP server ----
mcp = FastMCP("pydantic-docs")

# Auto-initialize on startup
_auto_initialize()

@mcp.tool(name="health_ping", description="Returns simple pong")
def ping() -> str:
    return "pong"

@mcp.tool(
    name="health_validate", description="Validate search indices and data integrity"
)
def validate() -> dict:
    """Check if all required data files exist and are valid."""
    is_valid, message = _validate_indices()
    
    return {
        "valid": is_valid,
        "message": message,
        "bm25_present": BM25_PATH.exists(),
        "records_present": RECORDS_PATH.exists(),
        "bm25_size_mb": BM25_PATH.stat().st_size / 1024 / 1024 if BM25_PATH.exists() else 0,
        "records_size_mb": RECORDS_PATH.stat().st_size / 1024 / 1024 if RECORDS_PATH.exists() else 0,
    }

@mcp.tool(name="pydantic_mode", description="Report data roots and offline mode.")
def t_mode() -> dict:
    def count_html(root: pathlib.Path) -> int:
        return sum(1 for _ in root.rglob("*.html")) if root.exists() else 0

    return {
        "offline_only": _OFFLINE_ONLY,
        "doc_root": str(DOC_ROOT),
        "doc_root_ai": str(DOC_ROOT_AI),
        "data_dir": str(DATA_DIR),
        "bm25_present": BM25_PATH.exists() and RECORDS_PATH.exists(),
        "counts": {
            "pydantic_html": count_html(DOC_ROOT),
            "pydantic_ai_html": count_html(DOC_ROOT_AI),
        },
        "display_bases": {"pydantic": LOCAL_BASE_P, "pydantic_ai": LOCAL_BASE_AI},
    }

@mcp.tool(
    name="pydantic_search",
    description="Search local Pydantic + Pydantic-AI docs with filters.",
)
async def t_search(
    query: str,
    k: int = 10,
    site: Optional[str] = None,  # "pydantic" | "pydantic_ai"
    heading: Optional[str] = None,  # matches heading title substring
    keywords: Optional[str] = None,  # space-separated required tokens
) -> SearchResponse:
    # k bounds
    try:
        k = max(1, min(50, int(k)))
    except Exception:
        k = 10

    # choose ranker
    hits = (
        _rank_hits_bm25(query, k * 3) if _HAS_BM25 else _rank_hits_mkdocs(query, k * 3)
    )

    # site filter
    if site in {"pydantic", "pydantic_ai"}:
        prefix = (
            "local://pydantic-ai/" if site == "pydantic_ai" else "local://pydantic/"
        )
        hits = [h for h in hits if h.get("url", "").startswith(prefix)]

    # heading filter (index-based for mkdocs; heuristic for bm25)
    if heading:
        hq = heading.lower()
        filtered = []
        for h in hits:
            rel = (
                h["url"].split("local://pydantic-ai/")[-1]
                if "pydantic-ai" in h["url"]
                else h["url"].split("local://pydantic/")[-1]
            )
            page = (
                next(
                    (
                        d
                        for d in (INDEX or {}).get("docs", [])
                        if d.get("location") == rel
                    ),
                    None,
                )
                if INDEX
                else None
            )
            match_title = None
            if page and "headings" in page:
                for hd in page["headings"]:
                    if hq in (hd.get("title", "").lower()):
                        match_title = hd.get("title")
                        break
            # if mkdocs index missing headings, fall back to snippet contains
            if match_title or (hq in h.get("snippet", "").lower()):
                h["heading_title"] = match_title
                filtered.append(h)
        hits = filtered

    # keywords filter (all tokens must appear in snippet or title)
    if keywords:
        toks = [t for t in re.split(r"\s+", keywords.strip()) if t]

        def ok(h: dict) -> bool:
            hay = (h.get("title", "") + " " + h.get("snippet", "")).lower()
            return all(t.lower() in hay for t in toks)

        hits = [h for h in hits if ok(h)]

    # trim to k
    hits = hits[:k]
    return SearchResponse(results=[SearchHit(**h) for h in hits])

@mcp.tool(
    name="pydantic_get",
    description="Fetch a local doc page and return plain text + html. Supports chunking for large documents via max_chars parameter.",
)
async def t_get(path_or_url: str, max_chars: Optional[int] = None) -> GetResponse:
    """
    Fetch a local documentation page.

    Args:
        path_or_url: Path or URL to the documentation page
        max_chars: Optional maximum characters for text and html. If provided and content exceeds this,
                  both text and html will be truncated. Useful for large API reference pages.
                  Default: None (no truncation)
    """
    root, rel = _safe_rel_from_url(path_or_url)
    html_str = _read_page(root, rel)
    text = BeautifulSoup(html_str, "lxml" if bs4_has_lxml() else "html.parser").get_text("\n")
    url = _display_url(root, rel)

    # Track original lengths
    text_length = len(text)
    html_length = len(html_str)
    truncated = False

    # Apply chunking if max_chars specified
    if max_chars and max_chars > 0:
        if text_length > max_chars:
            text = text[:max_chars] + "\n\n[... truncated ...]"
            truncated = True
        if html_length > max_chars:
            html_str = html_str[:max_chars] + "\n<!-- ... truncated ... -->"
            truncated = True

    try:
        return GetResponse(
            url=url,
            path=rel,
            text=text,
            html=html_str,
            truncated=truncated,
            text_length=text_length,
            html_length=html_length,
            max_chars=max_chars,
        )
    except ValidationError:
        return GetResponse(
            url=url,
            path=rel,
            text=text,
            html=html_str,
            truncated=truncated,
            text_length=text_length,
            html_length=html_length,
            max_chars=max_chars,
        )

@mcp.tool(
    name="pydantic_section",
    description="Extract a section by anchor from a local page.",
)
async def t_section(path_or_url: str, anchor: str) -> SectionResponse:
    root, rel = _safe_rel_from_url(path_or_url)
    html_str = _read_page(root, rel)
    section = _extract_section(html_str, anchor)
    url = _display_url(root, rel) + f"#{anchor}"
    try:
        return SectionResponse(url=url, path=rel, anchor=anchor, section=section, truncated=len(section) >= MAX_SECTION)
    except ValidationError:
        return SectionResponse(url=url, path=rel, anchor=anchor, section=section, truncated=len(section) >= MAX_SECTION)

API_ALIASES: Dict[str, str] = {
    "BaseModel": "api/base_model/",
    "TypeAdapter": "api/type_adapter/",
    "ValidationError": "api/errors/",
    "Settings": "concepts/pydantic_settings/",
}

@mcp.tool(
    name="pydantic_api",
    description="Jump to an API page by symbol name. Optional anchor.",
)
async def t_api(symbol: str, anchor: Optional[str] = None) -> Dict[str, Any]:
    rel = API_ALIASES.get(symbol) or "api/"
    root = DOC_ROOT
    rel_file = rel if rel.endswith(".html") else (rel + "index.html")
    html_str = _read_page(root, rel_file)
    if anchor:
        section = _extract_section(html_str, anchor)
        url = _display_url(root, rel) + f"#{anchor}"
        return {"symbol": symbol, "url": url, "section": section}
    text = BeautifulSoup(html_str, "lxml" if bs4_has_lxml() else "html.parser").get_text("\n")
    url = _display_url(root, rel)
    return {"symbol": symbol, "url": url, "text": text}

@mcp.tool(
    name="admin_rebuild_indices",
    description="Rebuild BM25 search indices from JSONL files. Use when indices are missing or corrupted.",
)
async def t_rebuild_indices() -> Dict[str, Any]:
    """Rebuild search indices from existing JSONL files."""
    try:
        from mcp_pydantic_docs.indexer import main as indexer_main
        
        # Check if JSONL files exist
        pydantic_jsonl = DATA_DIR / "pydantic.jsonl"
        pydantic_ai_jsonl = DATA_DIR / "pydantic_ai.jsonl"
        
        if not pydantic_jsonl.exists():
            return {"success": False, "message": "pydantic.jsonl not found. Download docs first."}
        if not pydantic_ai_jsonl.exists():
            return {"success": False, "message": "pydantic_ai.jsonl not found. Download docs first."}
        
        # Rebuild indices
        indexer_main()
        
        # Validate
        is_valid, msg = _validate_indices()
        
        return {
            "success": is_valid,
            "message": f"Indices rebuilt. {msg}",
            "bm25_size_mb": BM25_PATH.stat().st_size / 1024 / 1024 if BM25_PATH.exists() else 0,
            "records_size_mb": RECORDS_PATH.stat().st_size / 1024 / 1024 if RECORDS_PATH.exists() else 0,
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to rebuild indices: {e}"}

@mcp.tool(
    name="admin_cache_status",
    description="Get detailed status of documentation cache including file counts and sizes.",
)
async def t_cache_status() -> Dict[str, Any]:
    """cache status report."""
    def count_html(root: pathlib.Path) -> int:
        return sum(1 for _ in root.rglob("*.html")) if root.exists() else 0
    
    def count_jsonl_records(path: pathlib.Path) -> int:
        if not path.exists():
            return 0
        try:
            return len([line for line in path.read_text().strip().split('\n') if line.strip()])
        except Exception:
            return 0
    
    pydantic_docs = DOC_ROOT
    pydantic_ai_docs = DOC_ROOT_AI
    
    return {
        "paths": {
            "doc_root": str(DOC_ROOT),
            "doc_root_ai": str(DOC_ROOT_AI),
            "data_dir": str(DATA_DIR),
        },
        "documentation": {
            "pydantic": {
                "exists": pydantic_docs.exists(),
                "html_files": count_html(pydantic_docs) if pydantic_docs.exists() else 0,
            },
            "pydantic_ai": {
                "exists": pydantic_ai_docs.exists(),
                "html_files": count_html(pydantic_ai_docs) if pydantic_ai_docs.exists() else 0,
            },
        },
        "jsonl_data": {
            "pydantic": {
                "exists": (DATA_DIR / "pydantic.jsonl").exists(),
                "records": count_jsonl_records(DATA_DIR / "pydantic.jsonl"),
            },
            "pydantic_ai": {
                "exists": (DATA_DIR / "pydantic_ai.jsonl").exists(),
                "records": count_jsonl_records(DATA_DIR / "pydantic_ai.jsonl"),
            },
        },
        "search_indices": {
            "bm25_exists": BM25_PATH.exists(),
            "records_exists": RECORDS_PATH.exists(),
            "bm25_size_mb": BM25_PATH.stat().st_size / 1024 / 1024 if BM25_PATH.exists() else 0,
            "records_size_mb": RECORDS_PATH.stat().st_size / 1024 / 1024 if RECORDS_PATH.exists() else 0,
            "valid": _validate_indices()[0],
        },
        "offline_mode": _OFFLINE_ONLY,
    }

def main() -> None:
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()

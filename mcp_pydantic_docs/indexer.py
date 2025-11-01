# src/mcp_pydantic_docs/indexer.py
from __future__ import annotations

import json
import logging
import pathlib
import pickle
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag
from markdownify import markdownify as md

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_ENC: tiktoken.Encoding | None = None

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except ImportError as e:
    logger.warning("tiktoken not installed; token counting unavailable: %s", e)
except Exception as e:
    logger.error("Failed to initialize tiktoken encoder: %s", e, exc_info=True)


ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_P = ROOT / "docs_raw" / "pydantic"
RAW_AI = ROOT / "docs_raw" / "pydantic_ai"
RAW_SETTINGS = ROOT / "docs_raw" / "pydantic_settings"
MD_DIR = ROOT / "docs_md"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MD_DIR.mkdir(parents=True, exist_ok=True)

# --- boilerplate stripping and main-content focus ---
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

def tok_len(s: str) -> int:
    """Count tokens in string using cl100k_base encoding.

    Raises:
        RuntimeError: If tiktoken encoder is not available.
    """
    if _ENC is None:
        raise RuntimeError(
            "tiktoken encoder unavailable; ensure tiktoken is installed "
            "and cl100k_base encoding is accessible"
        )
    return len(_ENC.encode(s))

MAX_TOK = 1200  # target chunk size

def bs4_has_lxml() -> bool:
    try:
        import lxml  # noqa: F401

        return True
    except Exception:
        return False


def _clean_html_for_text(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml" if bs4_has_lxml() else "html.parser")
    for sel in _REMOVE_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    main: Tag | None = None
    for sel in _MAIN_SELECTORS:
        m = soup.select_one(sel)
        if isinstance(m, Tag):
            main = m
            break
    if main is not None:
        soup = BeautifulSoup(str(main), "lxml" if bs4_has_lxml() else "html.parser")
        for sel in _REMOVE_SELECTORS:
            for el in soup.select(sel):
                el.decompose()
    return soup


# --- markdown and cleaning ---
_FENCE = re.compile(r"`{3,}.*?`{3,}", re.S)
_PIPE_ROWS = re.compile(r"^\s*\|.*\|\s*$", re.M)
_LINE_NO_BURST = re.compile(r"(?:^|\s)(?:\d{1,4}\s+){5,}\d{1,4}(?=\s|$)")
_MULTI_WS = re.compile(r"\s+")


def to_markdown(html_fragment: str) -> str:
    m = md(html_fragment, heading_style="ATX")
    m = re.sub(r"```(\s*)\n```", "", m)
    m = _FENCE.sub(" ", m)
    m = _PIPE_ROWS.sub(" ", m)
    m = _LINE_NO_BURST.sub(" ", m)
    m = m.replace("|", " ").replace("`", " ")
    m = _MULTI_WS.sub(" ", m).strip()
    return m


# --- section extraction using REAL HTML anchors ---
def iter_sections(soup: BeautifulSoup) -> Iterable[Tuple[str | None, str, int, str]]:
    """
    Yield (anchor, heading_text, level, inner_html) for each h1/h2/h3 with id.
    If no headings with id exist, yield a single whole-page section with anchor=None.
    """
    headers: List[Tag] = [
        h for h in soup.select("h1[id],h2[id],h3[id]") if isinstance(h, Tag)
    ]
    if not headers:
        yield None, "", 0, str(soup)
        return
    for h in headers:
        anchor_raw = h.get("id")
        anchor = str(anchor_raw) if anchor_raw else None
        title = h.get_text(" ", strip=True)
        name = (h.name or "").lower()
        if not anchor or name not in {"h1", "h2", "h3"}:
            continue
        level = int(name[1])
        parts: List[str] = []
        for sib in h.next_siblings:
            if isinstance(sib, Tag):
                if sib.name and re.fullmatch(r"h[1-6]", sib.name):
                    if int(sib.name[1]) <= level:
                        break
                parts.append(str(sib))
        inner_html = "".join(parts)
        yield anchor, title, level, inner_html


def chunk_markdown(text: str, max_tok: int) -> List[str]:
    if tok_len(text) <= max_tok:
        return [text.strip()]
    out: List[str] = []
    acc: List[str] = []
    count = 0
    for para in text.split("\n\n"):
        t = tok_len(para)
        if acc and count + t > max_tok:
            out.append("\n\n".join(acc).strip())
            acc, count = [], 0
        acc.append(para)
        count += t
    if acc:
        out.append("\n\n".join(acc).strip())
    return [s for s in out if s]


def process_file(
    html_path: pathlib.Path, base_url: str, source_site: str
) -> List[Dict[str, Any]]:
    rel = html_path.relative_to(
        html_path.parents[0]
        if html_path.parent == html_path.parents[0]
        else html_path.parents[len(html_path.parts) - 2]
    ).as_posix()  # not used; replace below
    # reliable relative path:
    rel = html_path.as_posix().split("/docs_raw/", 1)[-1].split("/", 1)[-1]
    url = base_url.rstrip("/") + "/" + rel

    raw_html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = _clean_html_for_text(raw_html)

    # page-level markdown snapshot (debugging/inspection)
    page_md = to_markdown(str(soup))
    page_md_path = MD_DIR / (f"{source_site}-" + rel.replace("/", "_") + ".md")
    page_md_path.parent.mkdir(parents=True, exist_ok=True)
    page_md_path.write_text(page_md, encoding="utf-8")

    recs: List[Dict[str, Any]] = []
    for anchor, title, level, inner_html in iter_sections(soup):
        md_text = to_markdown(inner_html)
        title_out = title or (rel.rsplit("/", 1)[-1] if rel else "index")
        for chunk in chunk_markdown(md_text, MAX_TOK):
            recs.append(
                {
                    "title": title_out,
                    "anchor": anchor,
                    "heading_level": level,
                    "md_text": chunk,
                    "url": f"{url}#{anchor}" if anchor else url,
                    "page": rel,
                    "source_site": source_site,
                }
            )
    return recs


def _process_file_wrapper(args: tuple[pathlib.Path, str, str]) -> List[Dict[str, Any]]:
    """Wrapper for process_file to enable parallel processing."""
    html_path, base_url, source_site = args
    return process_file(html_path, base_url, source_site)


def process_site(
    raw_root: pathlib.Path,
    base_url: str,
    source_site: str,
    out_jsonl: pathlib.Path,
    max_workers: int | None = None,
) -> None:
    """Process all HTML files in a documentation site with parallel processing.

    Args:
        raw_root: Root directory containing HTML files
        base_url: Base URL for the documentation site
        source_site: Name of the source site
        out_jsonl: Output JSONL file path
        max_workers: Maximum number of worker processes (default: min(CPU count, 4))
    """
    import os

    # Use 50% of available CPU cores to keep system responsive
    if max_workers is None:
        cpu_count = os.cpu_count() or 1
        max_workers = max(2, cpu_count // 2)  # At least 2, at most 50% of cores
    if not raw_root.exists():
        logger.warning(f"Directory not found: {raw_root}")
        return

    html_files = sorted(list(raw_root.rglob("*.html")))
    if not html_files:
        logger.warning(f"No HTML files found in {raw_root}")
        return

    logger.info(f"Processing {len(html_files)} HTML files from {source_site}...")

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    # Prepare arguments for parallel processing
    args_list = [(html_path, base_url, source_site) for html_path in html_files]

    all_records = []

    # Process files in parallel
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_file_wrapper, args): args[0] for args in args_list
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
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"✓ Completed {source_site}: {len(all_records)} records")


def build_index(
    jsonl_files: List[pathlib.Path], output_name: str = "pydantic_all"
) -> None:
    """Build BM25 search index from JSONL files.

    Args:
        jsonl_files: List of JSONL files to index
        output_name: Base name for output index files
    """
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.error("rank-bm25 not installed. Run: uv add rank-bm25")
        return

    logger.info(f"Building BM25 index from {len(jsonl_files)} JSONL files...")

    # Load all records
    records = []
    for jsonl_path in jsonl_files:
        if not jsonl_path.exists():
            logger.warning(f"File not found: {jsonl_path}")
            continue
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

    logger.info(f"Loaded {len(records)} records")

    # Tokenize for BM25
    def tokenize(text: str) -> List[str]:
        text = text.lower()
        text = re.sub(r"[^a-z0-9_#\-\s]", " ", text)
        return [t for t in text.split() if len(t) > 1]

    corpus = [tokenize(r.get("md_text", "")) for r in records]

    logger.info("Building BM25 index...")
    bm25 = BM25Okapi(corpus)

    # Save index and records
    bm25_path = DATA_DIR / f"{output_name}_bm25.pkl"
    records_path = DATA_DIR / f"{output_name}_records.pkl"

    with bm25_path.open("wb") as f:
        pickle.dump(bm25, f)
    with records_path.open("wb") as f:
        pickle.dump(records, f)

    logger.info("✓ Index saved:")
    logger.info(f"  BM25: {bm25_path} ({bm25_path.stat().st_size / 1024 / 1024:.1f}MB)")
    logger.info(
        f"  Records: {records_path} ({records_path.stat().st_size / 1024 / 1024:.1f}MB)"
    )


def main() -> None:
    """Main entry point for building search indices with parallel processing."""
    import time

    start = time.time()

    logger.info("=" * 60)
    logger.info("BUILDING SEARCH INDICES")
    logger.info("=" * 60)

    process_site(
        RAW_P,
        "https://docs.pydantic.dev/latest",
        "pydantic",
        DATA_DIR / "pydantic.jsonl",
    )
    process_site(
        RAW_AI, "https://ai.pydantic.dev", "pydantic_ai", DATA_DIR / "pydantic_ai.jsonl"
    )
    if RAW_SETTINGS.exists():
        process_site(
            RAW_SETTINGS,
            "https://docs.pydantic.dev/latest/concepts/pydantic_settings",
            "pydantic_settings",
            DATA_DIR / "pydantic_settings.jsonl",
        )

    # Build BM25 index from all JSONL files
    jsonl_files = [
        DATA_DIR / "pydantic.jsonl",
        DATA_DIR / "pydantic_ai.jsonl",
    ]
    if (DATA_DIR / "pydantic_settings.jsonl").exists():
        jsonl_files.append(DATA_DIR / "pydantic_settings.jsonl")

    build_index(jsonl_files, "pydantic_all")

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info(f"✓ Index build complete in {elapsed:.1f}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

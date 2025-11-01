from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import tiktoken
from bs4 import BeautifulSoup
from bs4.element import Tag
from markdownify import markdownify as md

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


def _html_to_markdown(clean_html: str) -> str:
    """Convert cleaned HTML to markdown, preserving code blocks."""
    soup = BeautifulSoup(clean_html, "lxml" if bs4_has_lxml() else "html.parser")

    # Mark code blocks for preservation
    for pre in soup.find_all("pre"):
        pre["data-preserve"] = "1"

    # Convert to markdown
    md_text = md(str(soup), heading_style="ATX")

    # Clean up empty code blocks
    md_text = re.sub(r"```\s*\n\s*```", "", md_text)

    # Normalize excessive whitespace
    md_text = re.sub(r"\n{3,}", "\n\n", md_text)

    return md_text.strip()


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


def process_site(
    raw_root: pathlib.Path, base_url: str, out_jsonl: pathlib.Path
) -> None:
    """Process all HTML files in raw_root and write extracted sections to JSONL."""
    records = []
    for html_path in raw_root.rglob("*.html"):
        rel = html_path.relative_to(raw_root).as_posix()
        url = base_url.rstrip("/") + "/" + rel
        html = html_path.read_text(encoding="utf-8", errors="ignore")

        clean_html = _clean_html_for_text(html)
        md_text = _html_to_markdown(clean_html)
        sects = split_by_sections(md_text, url)

        # Write page-level markdown
        page_md_path = MD_DIR / (raw_root.name + "-" + rel.replace("/", "_") + ".md")
        page_md_path.parent.mkdir(parents=True, exist_ok=True)
        page_md_path.write_text(md_text, encoding="utf-8")

        for s in sects:
            s["page"] = rel
            s["source_site"] = raw_root.name
            records.append(s)

    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def main() -> None:
    """Main entry point for extracting docs to JSONL."""
    process_site(RAW_DIRS[0], "https://docs.pydantic.dev/latest", DATA_DIR/"pydantic.jsonl")
    process_site(RAW_DIRS[1], "https://ai.pydantic.dev", DATA_DIR/"pydantic_ai.jsonl")
    if RAW_DIRS[2].exists():
        process_site(RAW_DIRS[2], "https://docs.pydantic.dev/latest/concepts/pydantic_settings", DATA_DIR/"pydantic_settings.jsonl")

if __name__ == "__main__":
    main()

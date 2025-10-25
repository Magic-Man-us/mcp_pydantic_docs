from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Dict, List

import tiktoken
from bs4 import BeautifulSoup
from markdownify import markdownify as md

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

def clean_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    # remove obvious boilerplate
    for sel in ["nav", "header", "footer", ".toc", ".md-sidebar", ".navbar", ".feedback", ".admonition-title"]:
        for el in soup.select(sel):
            el.decompose()
    return soup

def page_to_markdown(soup: BeautifulSoup) -> str:
    # preserve code fences
    for pre in soup.find_all("pre"):
        pre["data-preserve"] = "1"
    m = md(str(soup), heading_style="ATX")
    # Fix code blocks
    m = re.sub(r"```(\s*)\n```", "", m)
    return m.strip()

def split_by_sections(md_text: str, base_url: str) -> List[Dict[str, Any]]:
    # split at H2/H3; keep anchor-like headings
    lines = md_text.splitlines()
    chunks = []
    current = {"title": None, "anchor": None, "body": []}

    def push():
        if current["title"] and current["body"]:
            body = "\n".join(current["body"]).strip()
            # token-aware sub-chunking
            toks = enc.encode(body)
            if len(toks) <= MAX_TOK:
                chunks.append({"title": current["title"], "anchor": current["anchor"], "md_text": body})
            else:
                # split on paragraphs to fit
                paras = body.split("\n\n")
                acc = []
                count = 0
                for p in paras:
                    ct = len(enc.encode(p))
                    if count + ct > MAX_TOK and acc:
                        chunks.append({"title": current["title"], "anchor": current["anchor"], "md_text": "\n\n".join(acc)})
                        acc, count = [], 0
                    acc.append(p); count += ct
                if acc:
                    chunks.append({"title": current["title"], "anchor": current["anchor"], "md_text": "\n\n".join(acc)})

    for ln in lines:
        if ln.startswith("## "):    # H2
            push()
            title = ln.lstrip("#").strip()
            anchor = re.sub(r"[^a-z0-9\- ]","",title.lower()).replace(" ","-")
            current = {"title": title, "anchor": anchor, "body": []}
        elif ln.startswith("### "):  # H3
            push()
            title = ln.lstrip("#").strip()
            anchor = re.sub(r"[^a-z0-9\- ]","",title.lower()).replace(" ","-")
            current = {"title": title, "anchor": anchor, "body": []}
        else:
            current["body"].append(ln)
    push()

    # attach URLs
    for c in chunks:
        c["url"] = base_url + (f"#{c['anchor']}" if c["anchor"] else "")
    return chunks

def process_site(raw_root: pathlib.Path, base_url: str, out_jsonl: pathlib.Path):
    records = []
    for html_path in raw_root.rglob("*.html"):
        rel = html_path.relative_to(raw_root).as_posix()
        url  = base_url.rstrip("/") + "/" + rel
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = clean_html(html)
        md_text = page_to_markdown(soup)
        sects = split_by_sections(md_text, url)
        # write page-level md
        page_md_path = MD_DIR / (raw_root.name + "-" + rel.replace("/","_") + ".md")
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

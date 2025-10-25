from __future__ import annotations

import json
import pathlib
import pickle
import re
from typing import Any, Dict, List

from rank_bm25 import BM25Okapi

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT/"data"

def load_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    items = []
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                items.append(json.loads(ln))
    return items

def tokenize(s: str) -> List[str]:
    s = s.lower()
    s = re.sub(r"[^a-z0-9_#\-\s]", " ", s)
    return [t for t in s.split() if len(t) > 1]

def build_index(in_paths: List[pathlib.Path], out_prefix: str):
    records = []
    for p in in_paths:
        records.extend(load_jsonl(p))
    corpus = [r.get("title","") + "\n" + r.get("md_text","") for r in records]
    tokenized = [tokenize(c) for c in corpus]
    bm25 = BM25Okapi(tokenized)
    (DATA_DIR/f"{out_prefix}_bm25.pkl").write_bytes(pickle.dumps(bm25))
    (DATA_DIR/f"{out_prefix}_records.pkl").write_bytes(pickle.dumps(records))

def main() -> None:
    """Main entry point for building search indices."""
    jsonl_files = [DATA_DIR/"pydantic.jsonl", DATA_DIR/"pydantic_ai.jsonl"]
    
    # Include pydantic_settings if it exists
    settings_jsonl = DATA_DIR/"pydantic_settings.jsonl"
    if settings_jsonl.exists():
        jsonl_files.append(settings_jsonl)
    
    build_index(jsonl_files, "pydantic_all")
    print(f"✅ Built search index from {len(jsonl_files)} sources")

if __name__ == "__main__":
    main()

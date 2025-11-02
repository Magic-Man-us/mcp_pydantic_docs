"""Setup script to download documentation and build search indices."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS_RAW = ROOT / "docs_raw"
DATA_DIR = ROOT / "data"


def download_and_extract_docs() -> bool:
    """
    Clone source repositories and extract documentation to JSONL format.
    
    This replaces the old HTML-based approach with direct extraction from
    source repositories (main branch), eliminating formatting artifacts.
    """
    print("📥 Cloning source repositories and extracting documentation...")

    try:
        from mcp_pydantic_docs.source_extractor import main as extractor_main
        
        # Create output directories
        DOCS_RAW.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Run source-based extraction
        success = extractor_main()
        
        if success:
            print("  ✅ Documentation extracted to JSONL")
        else:
            print("  ❌ Extraction failed")
        
        return success
    except Exception as e:
        print(f"  ❌ Failed to extract: {e}")
        import traceback
        traceback.print_exc()
        return False


def build_search_index() -> bool:
    """Build BM25 search indices from JSONL files."""
    print("🔍 Building search indices...")
    
    # Check if JSONL files exist
    pydantic_jsonl = DATA_DIR / "pydantic.jsonl"
    pydantic_ai_jsonl = DATA_DIR / "pydantic_ai.jsonl"
    
    if not pydantic_jsonl.exists() or not pydantic_ai_jsonl.exists():
        print("  ❌ JSONL files not found. Run with --download first.")
        return False
    
    try:
        from mcp_pydantic_docs.indexer import build_index
        
        build_index(
            [pydantic_jsonl, pydantic_ai_jsonl],
            "pydantic_all"
        )
        print("  ✅ Search indices built")
        return True
    except Exception as e:
        print(f"  ❌ Failed to build indices: {e}")
        return False


def clean_cache(force: bool = False) -> None:
    """Remove downloaded docs and built indices."""
    if not force:
        response = input("⚠️  This will delete all cached documentation. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled.")
            return
    
    print("🗑️  Cleaning cache...")
    
    if DOCS_RAW.exists():
        shutil.rmtree(DOCS_RAW)
        print(f"  ✅ Removed {DOCS_RAW}")
    
    if DATA_DIR.exists():
        for pkl_file in DATA_DIR.glob("*.pkl"):
            pkl_file.unlink()
            print(f"  ✅ Removed {pkl_file.name}")
        for jsonl_file in DATA_DIR.glob("*.jsonl"):
            jsonl_file.unlink()
            print(f"  ✅ Removed {jsonl_file.name}")


def check_status() -> None:
    """Check the current status of local cache."""
    print("📊 Cache Status:")
    print(f"  Root: {ROOT}")
    print()
    
    # Check source repositories
    pydantic_repo = DOCS_RAW / "pydantic"
    pydantic_ai_repo = DOCS_RAW / "pydantic_ai"
    
    print("  Source Repositories:")
    if pydantic_repo.exists():
        md_count = len(list(pydantic_repo.rglob("*.md")))
        py_count = len(list(pydantic_repo.rglob("*.py")))
        print(f"    ✅ Pydantic v2: {md_count} markdown + {py_count} Python files")
    else:
        print("    ❌ Pydantic v2: not cloned")
    
    if pydantic_ai_repo.exists():
        md_count = len(list(pydantic_ai_repo.rglob("*.md")))
        py_count = len(list(pydantic_ai_repo.rglob("*.py")))
        print(f"    ✅ Pydantic AI: {md_count} markdown + {py_count} Python files")
    else:
        print("    ❌ Pydantic AI: not cloned")
    
    print()
    print("  Search Data:")
    
    # Check JSONL
    pydantic_jsonl = DATA_DIR / "pydantic.jsonl"
    pydantic_ai_jsonl = DATA_DIR / "pydantic_ai.jsonl"
    
    if pydantic_jsonl.exists():
        lines = len(pydantic_jsonl.read_text().strip().split('\n'))
        print(f"    ✅ pydantic.jsonl: {lines} records")
    else:
        print("    ❌ pydantic.jsonl: not found")
    
    if pydantic_ai_jsonl.exists():
        lines = len(pydantic_ai_jsonl.read_text().strip().split('\n'))
        print(f"    ✅ pydantic_ai.jsonl: {lines} records")
    else:
        print("    ❌ pydantic_ai.jsonl: not found")
    
    # Check indices
    bm25_pkl = DATA_DIR / "pydantic_all_bm25.pkl"
    records_pkl = DATA_DIR / "pydantic_all_records.pkl"
    
    if bm25_pkl.exists() and records_pkl.exists():
        bm25_size = bm25_pkl.stat().st_size / 1024 / 1024
        records_size = records_pkl.stat().st_size / 1024 / 1024
        print(f"    ✅ Search indices: {bm25_size:.1f}MB + {records_size:.1f}MB")
    else:
        print("    ❌ Search indices: not built")


def main() -> int:
    """Main entry point for setup script."""
    parser = argparse.ArgumentParser(
        description="Setup local documentation cache for Pydantic MCP server"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download Pydantic and Pydantic AI documentation",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only download docs, don't build indices",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Extract JSONL and build search indices (requires downloaded docs)",
    )
    parser.add_argument(
        "--build-index-only",
        action="store_true",
        help="Only build indices from existing JSONL files",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove all cached documentation and indices",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check status of local cache",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing files",
    )
    
    args = parser.parse_args()
    
    if args.status:
        check_status()
        return 0
    
    if args.clean:
        clean_cache(force=args.force)
        return 0
    
    if not any([args.download, args.download_only, args.build_index, args.build_index_only]):
        parser.print_help()
        return 1
    
    success = True
    
    # Extract phase (clones repos and creates JSONL)
    if args.download or args.download_only or args.build_index:
        if args.force:
            if (DOCS_RAW / "pydantic").exists():
                shutil.rmtree(DOCS_RAW / "pydantic")
            if (DOCS_RAW / "pydantic_ai").exists():
                shutil.rmtree(DOCS_RAW / "pydantic_ai")
        
        if not args.build_index_only:
            success = download_and_extract_docs() and success
            
            if not success:
                print("\n❌ Extraction failed")
                return 1
    
    # Build index phase
    if (args.download or args.build_index or args.build_index_only) and not args.download_only:
        success = build_search_index() and success
    
    if success:
        print("\n✅ Setup complete! The MCP server is ready to use.")
        print("\n💡 Next steps:")
        print("  1. Configure the server in your MCP client (see README.md)")
        print("  2. Restart your MCP client")
        print("  3. Test with: pydantic_search(query='BaseModel')")
        return 0
    else:
        print("\n❌ Setup failed. See errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

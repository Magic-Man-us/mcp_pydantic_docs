"""Setup script to download documentation and build search indices."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS_RAW = ROOT / "docs_raw"
DATA_DIR = ROOT / "data"


def download_pydantic_docs() -> bool:
    """Download Pydantic v2 documentation."""
    print("📥 Downloading Pydantic v2 documentation...")
    target = DOCS_RAW / "pydantic"
    
    if target.exists():
        print(f"  ⚠️  {target} already exists. Use --force to overwrite.")
        return False
    
    target.parent.mkdir(parents=True, exist_ok=True)
    
    # Clone the docs repo (built docs are in gh-pages branch)
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                "--branch=gh-pages",
                "https://github.com/pydantic/pydantic.git",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
        print("  ✅ Pydantic docs downloaded")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to download: {e}")
        return False


def download_pydantic_ai_docs() -> bool:
    """Download Pydantic AI documentation."""
    print("📥 Downloading Pydantic AI documentation...")
    target = DOCS_RAW / "pydantic_ai"
    
    if target.exists():
        print(f"  ⚠️  {target} already exists. Use --force to overwrite.")
        return False
    
    target.parent.mkdir(parents=True, exist_ok=True)
    
    # Clone the AI docs repo (built docs are in gh-pages branch)
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                "--branch=gh-pages",
                "https://github.com/pydantic/pydantic-ai.git",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
        print("  ✅ Pydantic AI docs downloaded")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to download: {e}")
        return False


def download_pydantic_settings_docs() -> bool:
    """Download Pydantic Settings documentation."""
    print("📥 Downloading Pydantic Settings documentation...")
    target = DOCS_RAW / "pydantic_settings"
    
    if target.exists():
        print(f"  ⚠️  {target} already exists. Use --force to overwrite.")
        return False
    
    target.parent.mkdir(parents=True, exist_ok=True)
    
    # Clone the settings docs repo (built docs are in main branch site directory)
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                "--branch=main",
                "https://github.com/pydantic/pydantic-settings.git",
                str(target / "temp"),
            ],
            check=True,
            capture_output=True,
        )
        # Move the site directory to the target
        import shutil
        site_dir = target / "temp" / "site"
        if site_dir.exists():
            for item in site_dir.iterdir():
                shutil.move(str(item), str(target))
            shutil.rmtree(target / "temp")
            print("  ✅ Pydantic Settings docs downloaded")
            return True
        else:
            shutil.rmtree(target / "temp")
            print("  ❌ site directory not found in repo")
            return False
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to download: {e}")
        return False


def extract_to_jsonl() -> bool:
    """Extract HTML docs to JSONL format for indexing."""
    print("📝 Extracting documentation to JSONL...")
    
    try:
        from mcp_pydantic_docs.normalize import main as normalize_main
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        normalize_main()
        print("  ✅ JSONL files created")
        return True
    except Exception as e:
        print(f"  ❌ Failed to extract: {e}")
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
    
    # Check docs
    pydantic_docs = DOCS_RAW / "pydantic"
    pydantic_ai_docs = DOCS_RAW / "pydantic_ai"
    
    print("  Documentation:")
    if pydantic_docs.exists():
        html_count = len(list(pydantic_docs.rglob("*.html")))
        print(f"    ✅ Pydantic v2: {html_count} HTML files")
    else:
        print("    ❌ Pydantic v2: not downloaded")
    
    if pydantic_ai_docs.exists():
        html_count = len(list(pydantic_ai_docs.rglob("*.html")))
        print(f"    ✅ Pydantic AI: {html_count} HTML files")
    else:
        print("    ❌ Pydantic AI: not downloaded")
    
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
    
    # Download phase
    if args.download or args.download_only:
        if args.force:
            if (DOCS_RAW / "pydantic").exists():
                shutil.rmtree(DOCS_RAW / "pydantic")
            if (DOCS_RAW / "pydantic_ai").exists():
                shutil.rmtree(DOCS_RAW / "pydantic_ai")
        
        success = download_pydantic_docs() and success
        success = download_pydantic_ai_docs() and success
        
        if not success:
            print("\n❌ Download failed")
            return 1
    
    # Build phase
    if args.download or args.build_index:
        if not args.download_only:
            success = extract_to_jsonl() and success
            success = build_search_index() and success
    elif args.build_index_only:
        success = build_search_index() and success
    
    if success:
        print("\n✅ Setup complete! The MCP server is ready to use.")
        print("\n💡 Next steps:")
        print("  1. Configure the server in your MCP client (see README.md)")
        print("  2. Restart your MCP client")
        print("  3. Test with: pydantic.search(query='BaseModel')")
        return 0
    else:
        print("\n❌ Setup failed. See errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

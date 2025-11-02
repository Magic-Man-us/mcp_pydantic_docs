# Pydantic Documentation MCP Server

A Model Context Protocol (MCP) server providing local-first access to Pydantic and Pydantic AI documentation with BM25-powered full-text search.

## Features

- **Local-first architecture** - Offline-only mode by default
- **BM25 full-text search** - Fast semantic search across all docs
- **Git-based extraction** - Direct from source repositories (no HTML scraping)
- **Pre-processed data** - JSONL files included for instant setup
- **Auto-initialization** - Builds indices automatically on first run
- **Complete coverage** - Pydantic v2 and Pydantic AI documentation

## Requirements

- Python 3.12+
- uv package manager
- ~15MB disk space (with indices)

## Quick Start

```bash
# Clone and install
git clone <repository-url>
cd mcp_pydantic_docs
uv sync

# Server auto-builds indices on first run
uv run mcp-pydantic-docs
```

## MCP Client Configuration

Add to your MCP settings (e.g., `cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "pydantic-docs": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp_pydantic_docs",
        "run",
        "mcp-pydantic-docs"
      ]
    }
  }
}
```

## Architecture

### How It Works

1. **Source Extraction** (`source_extractor.py`) - Clones Pydantic repos, extracts documentation from markdown/docstrings → JSONL
2. **Index Building** (`indexer.py`) - Processes JSONL files → BM25 search indices
3. **MCP Server** (`mcp.py`) - Serves documentation via MCP tools
4. **Shared Utilities** (`utils.py`) - HTML/text processing, normalization

### Directory Structure

```
mcp_pydantic_docs/
├── mcp_pydantic_docs/          # Source code
│   ├── mcp.py                  # MCP server
│   ├── source_extractor.py     # Git-based doc extraction
│   ├── indexer.py              # BM25 index builder
│   ├── utils.py                # Shared utilities
│   └── setup.py                # Setup CLI
├── data/                       # Search data
│   ├── pydantic.jsonl          # Pydantic docs (2.9MB, in git)
│   ├── pydantic_ai.jsonl       # Pydantic AI docs (3.3MB, in git)
│   ├── *_bm25.pkl              # BM25 index (generated)
│   └── *_records.pkl           # Document records (generated)
└── docs_raw/                   # Source repos (not in git)
    ├── pydantic/               # Cloned from GitHub
    └── pydantic_ai/            # Cloned from GitHub
```

### Data Flow

```
GitHub Repos → source_extractor.py → JSONL files → indexer.py → BM25 indices → mcp.py → MCP Client
```

## Available Tools

### Search & Retrieval

- **`pydantic_search(query, k=10)`** - Full-text search with BM25 ranking
- **`pydantic_get(path_or_url, max_chars=None)`** - Fetch full documentation page
- **`pydantic_section(path_or_url, anchor)`** - Extract specific section
- **`pydantic_api(symbol, anchor=None)`** - Jump to API documentation

### Health & Admin

- **`health_ping()`** - Server health check
- **`health_validate()`** - Validate search indices
- **`pydantic_mode()`** - Server configuration
- **`admin_cache_status()`** - Detailed cache status
- **`admin_rebuild_indices()`** - Rebuild search indices

## Updating Documentation

### Rebuild from Existing JSONL

```bash
uv run python -m mcp_pydantic_docs.indexer
```

### Extract Fresh Documentation

```bash
# Check status
uv run python -m mcp_pydantic_docs.setup --status

# Download and extract from GitHub
uv run python -m mcp_pydantic_docs.setup --download --build-index

# Clean cache
uv run python -m mcp_pydantic_docs.setup --clean
```

## Configuration

### Environment Variables

- `PDA_DOC_ROOT` - Pydantic v2 source path
- `PDA_DOC_ROOT_AI` - Pydantic AI source path
- `PDA_DATA_DIR` - Data directory path

### Offline Mode

Default: **Enabled** (`OFFLINE_ONLY = True` in `mcp.py`)

- Blocks remote requests
- Validates file paths
- All content from local cache

## Development

### Run Tests

```bash
uv run pytest
```

### Code Quality

```bash
uv run black mcp_pydantic_docs/  # Format
uv run ruff check .              # Lint
uv run mypy mcp_pydantic_docs/   # Type check
```

## Troubleshooting

**Search indices not found:**
```bash
uv run python -m mcp_pydantic_docs.indexer
```

**Wrong Python version:**
```bash
uv python install 3.12
```

**Server won't start:**
```bash
# Test standalone
uv run mcp-pydantic-docs

# Check indices
uv run python -m mcp_pydantic_docs.setup --status
```

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Code style
- Testing requirements
- Pull request process

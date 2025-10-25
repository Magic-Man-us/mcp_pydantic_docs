# Pydantic Documentation MCP Server

A Model Context Protocol (MCP) server providing local-first access to Pydantic and Pydantic AI documentation with BM25-powered full-text search.

## Features

- Local-first architecture with offline-only mode (configurable)
- BM25 full-text search across all documentation
- Pre-processed JSONL data included for fast setup
- Intelligent path resolution (no hardcoded paths)
- Complete coverage of Pydantic v2 and Pydantic AI documentation
- Path validation and security controls

## Requirements

- Python 3.12+
- uv package manager
- ~15MB disk space (with indices)

## Quick Start

```bash
# Clone repository
git clone <repository-url>
cd mcp_pydantic_docs

# Create virtual environment and install dependencies
uv sync

# The server will auto-build indices on first run
# Or manually build them:
uv run python -m mcp_pydantic_docs.indexer

# Verify installation
uv run mcp-pydantic-docs
```

**Note:** The server automatically builds search indices from included JSONL files on first startup if they don't exist. This typically takes 5-10 seconds.

## Installation

### Development Setup

1. **Create virtual environment and install dependencies:**
```bash
cd mcp_pydantic_docs
uv sync
```

This creates `.venv/` and installs all dependencies from `pyproject.toml`.

2. **Build search indices:**
```bash
uv run python -m mcp_pydantic_docs.indexer
```

Generates:
- `data/pydantic_all_bm25.pkl` (~3.2MB)
- `data/pydantic_all_records.pkl` (~6MB)

3. **Test the server:**
```bash
uv run mcp-pydantic-docs
```

### Production Deployment

**Option 1: Direct execution with uv**
```bash
uv --directory /path/to/mcp_pydantic_docs run mcp-pydantic-docs
```

**Option 2: Build and install wheel**
```bash
# Build distribution
uv build

# Install wheel
uv pip install dist/mcp_pydantic_docs-0.1.0-py3-none-any.whl

# Run
mcp-pydantic-docs
```

**Option 3: Install in editable mode**
```bash
uv pip install -e /path/to/mcp_pydantic_docs
```

## MCP Client Configuration

Add to your MCP settings (e.g., `cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "pydantic-docs": {
      "disabled": false,
      "timeout": 60,
      "type": "stdio",
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

Replace `/absolute/path/to/mcp_pydantic_docs` with your installation path.

## Architecture

### Directory Structure

```
mcp_pydantic_docs/
├── pyproject.toml              # Package configuration
├── uv.lock                     # Locked dependencies
├── mcp_pydantic_docs/          # Source code
│   ├── __init__.py
│   ├── mcp.py                  # MCP server implementation
│   ├── indexer.py              # BM25 index builder
│   ├── normalize.py            # HTML to JSONL converter
│   └── setup.py                # Setup utilities
├── data/                       # Search data (in git: JSONL only)
│   ├── pydantic.jsonl          # Pydantic docs (2.9MB)
│   ├── pydantic_ai.jsonl       # Pydantic AI docs (3.3MB)
│   ├── pydantic_all_bm25.pkl   # BM25 index (generated)
│   └── pydantic_all_records.pkl # Document records (generated)
├── docs_raw/                   # Raw HTML (not in git)
│   ├── pydantic/
│   └── pydantic_ai/
└── docs_md/                    # Markdown cache (not in git)
```

### Path Resolution

The server automatically locates data directories:

1. Searches up from `mcp.py` for `data/` or `docs_raw/`
2. Falls back to relative paths from package directory
3. Can be overridden with environment variables:
   - `PDA_DOC_ROOT` - Path to Pydantic v2 HTML docs
   - `PDA_DOC_ROOT_AI` - Path to Pydantic AI HTML docs
   - `PDA_DATA_DIR` - Path to data directory

## Available Tools

### Health Checks

**`health.ping`**
```python
Returns: "pong"
```

**`health.validate`**
```python
Returns: {
  "valid": bool,
  "message": str,
  "bm25_present": bool,
  "records_present": bool,
  "bm25_size_mb": float,
  "records_size_mb": float
}
```

### Documentation Access

**`pydantic.search`**
```python
Parameters:
  - query: str (search query)
  - k: int = 10 (number of results)

Returns: SearchResponse {
  "results": [
    {
      "title": str,
      "url": str,
      "anchor": str | null,
      "snippet": str
    }
  ]
}
```

**`pydantic.get`**
```python
Parameters:
  - path_or_url: str (relative path or full URL)

Returns: GetResponse {
  "url": str,
  "path": str,
  "text": str,
  "html": str
}
```

**`pydantic.section`**
```python
Parameters:
  - path_or_url: str
  - anchor: str (section ID)

Returns: SectionResponse {
  "url": str,
  "path": str,
  "anchor": str,
  "section": str,
  "truncated": bool
}
```

**`pydantic.api`**
```python
Parameters:
  - symbol: str (e.g., "BaseModel", "TypeAdapter")
  - anchor: str | null (optional section)

Returns: dict {
  "symbol": str,
  "url": str,
  "section": str | "text": str
}
```

### Administration

**`pydantic.mode`**
```python
Returns: {
  "offline_only": bool,
  "doc_root": str,
  "doc_root_ai": str,
  "data_dir": str,
  "bm25_present": bool,
  "counts": {
    "pydantic_html": int,
    "pydantic_ai_html": int
  },
  "display_bases": dict
}
```

**`admin.cache_status`**
```python
Returns: {
  "paths": dict,
  "documentation": dict,
  "jsonl_data": dict,t
  "search_indices": dict,
  "offline_mode": bool
}
```

**`admin.rebuild_indices`**
```python
Returns: {
  "success": bool,
  "message": str,
  "bm25_size_mb": float,
  "records_size_mb": float
}
```

## Updating Documentation

### Rebuild Indices

```bash
uv run python -m mcp_pydantic_docs.indexer
```

### Download Latest Documentation

```bash
# Check current status
uv run python -m mcp_pydantic_docs.setup --status

# Download and build indices
uv run python -m mcp_pydantic_docs.setup --download --build-index

# Force re-download
uv run python -m mcp_pydantic_docs.setup --download --force

# Clean cache
uv run python -m mcp_pydantic_docs.setup --clean
```

## Security

### Offline Mode (Default)

- `OFFLINE_ONLY = True` in `mcp.py`
- Blocks all HTTP/HTTPS requests except known base URLs as identifiers
- File path validation prevents directory traversal
- All content served from local cache

### Enabling Online Fallback

Edit `mcp_pydantic_docs/mcp.py`:
```python
OFFLINE_ONLY = False  # Allow remote fetching
```

**Note:** Online mode is not recommended for production use.

## Development

### Running Tests

```bash
uv run pytest
```

### Code Quality

```bash
# Format code
uv run black mcp_pydantic_docs/

# Lint
uv run ruff check mcp_pydantic_docs/

# Type check
uv run mypy mcp_pydantic_docs/
```

### Building Package

```bash
# Build wheel and sdist
uv build

# Output: dist/mcp_pydantic_docs-0.1.0-py3-none-any.whl
#         dist/mcp_pydantic_docs-0.1.0.tar.gz
```

## Git Strategy

### Included in Repository
- Source code
- `uv.lock` (reproducible builds)
- `data/*.jsonl` (~6MB, pre-processed data)
- Documentation and configuration

### Excluded from Repository
- `.venv/` (virtual environment)
- `data/*.pkl` (binary indices, rebuilt from JSONL)
- `docs_raw/` (45MB HTML, downloadable)
- `docs_md/` (derived data)

## Troubleshooting

### Search indices not found

```bash
uv run python -m mcp_pydantic_docs.indexer
```

### Wrong Python version

Ensure Python 3.12+ is active:
```bash
uv python list
uv python install 3.12
```

### Path resolution fails

Set explicit paths:
```bash
export PDA_DATA_DIR=/path/to/mcp_pydantic_docs/data
export PDA_DOC_ROOT=/path/to/mcp_pydantic_docs/docs_raw/pydantic
export PDA_DOC_ROOT_AI=/path/to/mcp_pydantic_docs/docs_raw/pydantic_ai
```

### MCP connection issues

Verify server runs standalone:
```bash
uv run mcp-pydantic-docs
# Should start and listen on stdio
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:

- Development setup
- Code style and standards
- Testing requirements
- Pull request process
- Commit message conventions

For bugs and feature requests, please open an issue on GitHub.

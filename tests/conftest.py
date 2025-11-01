"""Pytest configuration and fixtures for MCP Pydantic Docs tests."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def data_dir(project_root: Path) -> Path:
    """Get the data directory."""
    return project_root / "data"


@pytest.fixture(scope="session")
def docs_raw_dir(project_root: Path) -> Path:
    """Get the raw docs directory."""
    return project_root / "docs_raw"


@pytest.fixture(scope="session")
def search_indices_exist(data_dir: Path) -> bool:
    """Check if search indices exist."""
    bm25_path = data_dir / "pydantic_all_bm25.pkl"
    records_path = data_dir / "pydantic_all_records.pkl"
    return bm25_path.exists() and records_path.exists()


@pytest.fixture(scope="session")
def jsonl_files_exist(data_dir: Path) -> bool:
    """Check if JSONL files exist."""
    pydantic_jsonl = data_dir / "pydantic.jsonl"
    pydantic_ai_jsonl = data_dir / "pydantic_ai.jsonl"
    return pydantic_jsonl.exists() and pydantic_ai_jsonl.exists()


@pytest.fixture(scope="session")
def sample_search_queries() -> list[str]:
    """Sample search queries for testing."""
    return [
        "BaseModel",
        "validation",
        "field",
        "TypeAdapter",
        "pydantic_core",
    ]


@pytest.fixture(scope="session")
def sample_page_paths() -> list[str]:
    """Sample page paths for testing."""
    return [
        "api/base_model/index.html",
        "concepts/models/index.html",
        "concepts/fields/index.html",
    ]


@pytest.fixture(scope="session")
def sample_api_symbols() -> list[str]:
    """Sample API symbols for testing."""
    return [
        "BaseModel",
        "TypeAdapter",
        "Field",
        "ValidationError",
        "ConfigDict",
    ]


@pytest.fixture(scope="session")
def sample_anchors() -> dict[str, list[str]]:
    """Sample anchors for section extraction testing."""
    return {
        "api/base_model/index.html": [
            "pydantic.BaseModel.model_dump",
            "pydantic.BaseModel.model_validate",
            "pydantic.BaseModel.model_copy",
        ]
    }


@pytest.fixture
def skip_if_no_indices(search_indices_exist: bool):
    """Skip test if search indices don't exist."""
    if not search_indices_exist:
        pytest.skip("Search indices not found. Run: uv run python -m mcp_pydantic_docs.indexer")


@pytest.fixture
def skip_if_no_docs(docs_raw_dir: Path):
    """Skip test if documentation files don't exist."""
    pydantic_dir = docs_raw_dir / "pydantic"
    pydantic_ai_dir = docs_raw_dir / "pydantic_ai"
    
    if not (pydantic_dir.exists() and pydantic_ai_dir.exists()):
        pytest.skip("Documentation files not found. Run: uv run python -m mcp_pydantic_docs.setup --download")

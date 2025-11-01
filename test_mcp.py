"""Comprehensive tests for MCP Pydantic Docs server.

Run with: pytest test_mcp.py -v
Run specific markers: pytest test_mcp.py -v -m health
"""

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


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent


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


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

from mcp_pydantic_docs.mcp import ping, validate


@pytest.mark.health
class TestHealthChecks:
    """Test health check functionality."""

    def test_ping_returns_pong(self):
        """Test that ping returns 'pong'."""
        result = ping()
        assert result == "pong", "ping() should return 'pong'"

    def test_validate_returns_dict(self, skip_if_no_indices):
        """Test that validate returns a dictionary."""
        result = validate()
        assert isinstance(result, dict), "validate() should return a dict"

    def test_validate_has_required_keys(self, skip_if_no_indices):
        """Test that validate response has required keys."""
        result = validate()
        required_keys = ["valid", "message", "bm25_present", "records_present"]
        for key in required_keys:
            assert key in result, f"validate() response missing key: {key}"

    def test_validate_indices_valid(self, skip_if_no_indices):
        """Test that validation passes when indices exist."""
        result = validate()
        assert result["valid"] is True, "Indices should be valid"
        assert result["bm25_present"] is True, "BM25 index should be present"
        assert result["records_present"] is True, "Records should be present"

    def test_validate_has_size_info(self, skip_if_no_indices):
        """Test that validate returns size information."""
        result = validate()
        assert "bm25_size_mb" in result, "Missing BM25 size info"
        assert "records_size_mb" in result, "Missing records size info"
        
        assert isinstance(result["bm25_size_mb"], (int, float)), "BM25 size should be numeric"
        assert isinstance(result["records_size_mb"], (int, float)), "Records size should be numeric"
        
        assert result["bm25_size_mb"] > 0, "BM25 size should be positive"
        assert result["records_size_mb"] > 0, "Records size should be positive"

    def test_validate_message_informative(self, skip_if_no_indices):
        """Test that validate message is informative."""
        result = validate()
        assert len(result["message"]) > 0, "Message should not be empty"
        assert isinstance(result["message"], str), "Message should be a string"


# ============================================================================
# SEARCH TESTS
# ============================================================================

from mcp_pydantic_docs.mcp import t_search


@pytest.mark.search
class TestSearch:
    """Test search functionality."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, skip_if_no_indices, sample_search_queries):
        """Test that search returns results for valid queries."""
        for query in sample_search_queries:
            result = await t_search(query=query, k=5)
            assert hasattr(result, "results"), f"Search result should have 'results' attribute for query: {query}"

    @pytest.mark.asyncio
    async def test_search_basemodel(self, skip_if_no_indices):
        """Test search for BaseModel returns results."""
        result = await t_search(query="BaseModel", k=5)
        assert len(result.results) > 0, "Search for 'BaseModel' should return results"
        
        # Check first result has expected attributes
        first = result.results[0]
        assert hasattr(first, "title"), "Result should have title"
        assert hasattr(first, "url"), "Result should have url"
        assert hasattr(first, "snippet"), "Result should have snippet"

    @pytest.mark.asyncio
    async def test_search_with_k_parameter(self, skip_if_no_indices):
        """Test that k parameter limits results."""
        k_values = [1, 3, 5, 10]
        
        for k in k_values:
            result = await t_search(query="validation", k=k)
            assert len(result.results) <= k, f"Should return at most {k} results"

    @pytest.mark.asyncio
    async def test_search_with_site_filter(self, skip_if_no_indices):
        """Test search with site filter."""
        result = await t_search(query="validation", k=5, site="pydantic")
        assert hasattr(result, "results"), "Filtered search should return results"
        
        # All results should be from pydantic site
        for item in result.results:
            assert "pydantic" in item.url.lower() or "local://pydantic" in item.url.lower(), \
                f"Result should be from pydantic site: {item.url}"

    @pytest.mark.asyncio
    async def test_search_with_keywords(self, skip_if_no_indices):
        """Test search with keyword filter."""
        result = await t_search(query="field", k=5, keywords="default")
        assert hasattr(result, "results"), "Keyword filtered search should return results"

    @pytest.mark.asyncio
    async def test_search_result_structure(self, skip_if_no_indices):
        """Test that search results have correct structure."""
        result = await t_search(query="BaseModel", k=3)
        
        for item in result.results:
            # Check required attributes exist
            assert hasattr(item, "title"), "Result must have title"
            assert hasattr(item, "url"), "Result must have url"
            assert hasattr(item, "snippet"), "Result must have snippet"
            
            # Check types
            assert isinstance(item.title, str), "Title should be string"
            assert isinstance(item.url, str), "URL should be string"
            assert isinstance(item.snippet, str), "Snippet should be string"
            
            # Check content
            assert len(item.title) > 0, "Title should not be empty"
            assert len(item.url) > 0, "URL should not be empty"
            assert len(item.snippet) > 0, "Snippet should not be empty"

    @pytest.mark.asyncio
    async def test_search_empty_query(self, skip_if_no_indices):
        """Test search with empty query."""
        result = await t_search(query="", k=5)
        # Should either return empty results or handle gracefully
        assert hasattr(result, "results"), "Should handle empty query"

    @pytest.mark.asyncio
    async def test_search_special_characters(self, skip_if_no_indices):
        """Test search with special characters."""
        special_queries = [
            "model_dump",
            "Field[str]",
            "__init__",
            "type: int",
        ]
        
        for query in special_queries:
            result = await t_search(query=query, k=5)
            assert hasattr(result, "results"), f"Should handle special characters: {query}"


# ============================================================================
# DOCUMENT RETRIEVAL TESTS
# ============================================================================

from mcp_pydantic_docs.mcp import t_api, t_get, t_section


@pytest.mark.retrieval
class TestDocumentRetrieval:
    """Test document retrieval functionality."""

    @pytest.mark.asyncio
    async def test_get_full_page(self, skip_if_no_docs):
        """Test retrieving a full page."""
        result = await t_get("api/base_model/index.html")
        
        assert hasattr(result, "text"), "Result should have text"
        assert hasattr(result, "html"), "Result should have html"
        assert hasattr(result, "url"), "Result should have url"
        assert hasattr(result, "path"), "Result should have path"
        
        assert len(result.text) > 0, "Text should not be empty"
        assert len(result.html) > 0, "HTML should not be empty"

    @pytest.mark.asyncio
    async def test_get_text_length(self, skip_if_no_docs):
        """Test that text length is reported correctly."""
        result = await t_get("api/base_model/index.html")
        
        assert hasattr(result, "text_length"), "Should have text_length"
        assert result.text_length == len(result.text), "text_length should match actual text length"

    @pytest.mark.asyncio
    async def test_get_html_length(self, skip_if_no_docs):
        """Test that HTML length is reported correctly."""
        result = await t_get("api/base_model/index.html")
        
        assert hasattr(result, "html_length"), "Should have html_length"
        assert result.html_length == len(result.html), "html_length should match actual HTML length"

    @pytest.mark.asyncio
    async def test_get_with_chunking(self, skip_if_no_docs):
        """Test page retrieval with max_chars limit."""
        max_chars = 50000
        result = await t_get("api/base_model/index.html", max_chars=max_chars)
        
        assert hasattr(result, "truncated"), "Should have truncated flag"
        
        # If page is larger than max_chars, should be truncated
        if result.text_length > max_chars:
            assert result.truncated is True, "Should be marked as truncated"
            assert len(result.text) <= max_chars + 100, "Text should be truncated near max_chars"
            assert len(result.html) <= max_chars + 100, "HTML should be truncated near max_chars"

    @pytest.mark.asyncio
    async def test_get_no_truncation_for_small_pages(self, skip_if_no_docs):
        """Test that small pages are not truncated."""
        result = await t_get("api/base_model/index.html", max_chars=500000)
        
        if result.text_length < 500000:
            assert result.truncated is False, "Small page should not be truncated"

    @pytest.mark.asyncio
    async def test_get_invalid_path(self, skip_if_no_docs):
        """Test that invalid path raises appropriate error."""
        with pytest.raises(Exception):
            await t_get("nonexistent/page.html")

    @pytest.mark.asyncio
    async def test_section_extraction(self, skip_if_no_docs):
        """Test extracting a specific section."""
        result = await t_section(
            "api/base_model/index.html",
            "pydantic.BaseModel.model_dump"
        )
        
        assert hasattr(result, "section"), "Should have section"
        assert hasattr(result, "anchor"), "Should have anchor"
        assert hasattr(result, "url"), "Should have url"
        assert hasattr(result, "path"), "Should have path"
        
        assert len(result.section) > 0, "Section should not be empty"
        assert result.anchor == "pydantic.BaseModel.model_dump", "Anchor should match"

    @pytest.mark.asyncio
    async def test_section_truncation(self, skip_if_no_docs):
        """Test that sections can be truncated."""
        result = await t_section(
            "api/base_model/index.html",
            "pydantic.BaseModel.model_dump"
        )
        
        assert hasattr(result, "truncated"), "Should have truncated flag"
        assert isinstance(result.truncated, bool), "truncated should be boolean"

    @pytest.mark.asyncio
    async def test_section_invalid_anchor(self, skip_if_no_docs):
        """Test section extraction with invalid anchor."""
        with pytest.raises(Exception):
            await t_section(
                "api/base_model/index.html",
                "nonexistent.anchor.here"
            )

    @pytest.mark.asyncio
    async def test_api_symbol_lookup(self, skip_if_no_docs, sample_api_symbols):
        """Test API symbol lookup."""
        for symbol in sample_api_symbols:
            result = await t_api(symbol)
            
            assert isinstance(result, dict), f"Result should be dict for {symbol}"
            assert "symbol" in result, f"Should have symbol for {symbol}"
            assert "url" in result, f"Should have url for {symbol}"
            assert result["symbol"] == symbol, f"Symbol should match: {symbol}"

    @pytest.mark.asyncio
    async def test_api_basemodel(self, skip_if_no_docs):
        """Test API lookup for BaseModel."""
        result = await t_api("BaseModel")
        
        assert result["symbol"] == "BaseModel"
        assert "url" in result
        assert "text" in result or "section" in result, "Should have either text or section"
        
        content_key = "text" if "text" in result else "section"
        assert len(result[content_key]) > 0, "Content should not be empty"

    @pytest.mark.asyncio
    async def test_api_with_anchor(self, skip_if_no_docs):
        """Test API lookup with specific anchor."""
        result = await t_api("BaseModel", anchor="pydantic.BaseModel.model_validate")
        
        assert result["symbol"] == "BaseModel"
        assert "url" in result
        assert "#pydantic.BaseModel.model_validate" in result["url"], "URL should include anchor"
        assert "section" in result, "Should return section when anchor specified"

    @pytest.mark.asyncio
    async def test_api_invalid_symbol(self, skip_if_no_docs):
        """Test API lookup with invalid symbol."""
        with pytest.raises(Exception):
            await t_api("CompletelyNonexistentSymbol123")

    @pytest.mark.asyncio
    async def test_get_multiple_pages(self, skip_if_no_docs, sample_page_paths):
        """Test retrieving multiple different pages."""
        for path in sample_page_paths:
            try:
                result = await t_get(path)
                assert len(result.text) > 0, f"Page {path} should have content"
            except FileNotFoundError:
                # Some sample paths may not exist, which is okay
                pass

    @pytest.mark.asyncio
    async def test_text_is_cleaned(self, skip_if_no_docs):
        """Test that retrieved text is cleaned."""
        result = await t_get("api/base_model/index.html")
        
        # Check that excessive whitespace is reduced
        assert "\n\n\n\n" not in result.text, "Should not have 4+ consecutive newlines"
        
        # HTML should be longer than text (tags removed)
        assert len(result.html) > len(result.text), "HTML should be longer than text"

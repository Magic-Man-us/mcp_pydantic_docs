"""Tests for search functionality."""

from __future__ import annotations

import pytest

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

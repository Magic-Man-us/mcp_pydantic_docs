"""Tests for document retrieval functionality."""

from __future__ import annotations

import pytest

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

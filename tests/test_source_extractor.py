"""Tests for source-based documentation extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcp_pydantic_docs.source_extractor import (
    PYDANTIC_AI_CONFIG,
    PYDANTIC_CONFIG,
    DocumentChunk,
    PythonSymbolDoc,
    build_api_url,
    chunk_text,
    clean_docstring,
    extract_heading_info,
)


class TestDocumentChunk:
    """Test DocumentChunk Pydantic model."""

    def test_valid_chunk(self):
        """Test creating a valid document chunk."""
        chunk = DocumentChunk(
            title="Test Title",
            anchor="test-anchor",
            heading_level=2,
            md_text="Test content",
            url="https://docs.pydantic.dev/latest/concepts/models/",
            page="concepts/models",
            source_site="pydantic",
        )
        assert chunk.title == "Test Title"
        assert chunk.anchor == "test-anchor"
        assert chunk.heading_level == 2
        assert chunk.md_text == "Test content"

    def test_chunk_to_jsonl(self):
        """Test converting chunk to JSONL format."""
        chunk = DocumentChunk(
            title="Test",
            anchor=None,
            heading_level=0,
            md_text="Content",
            url="https://example.com",
            page="page",
            source_site="pydantic",
        )
        jsonl = chunk.to_jsonl()
        assert jsonl["title"] == "Test"
        assert jsonl["anchor"] is None
        assert jsonl["heading_level"] == 0
        assert "source_site" in jsonl

    def test_invalid_source_site(self):
        """Test that invalid source_site values are rejected."""
        with pytest.raises(ValidationError):
            DocumentChunk(
                title="Test",
                anchor=None,
                heading_level=0,
                md_text="Content",
                url="https://example.com",
                page="page",
                source_site="invalid_site",
            )


class TestPythonSymbolDoc:
    """Test PythonSymbolDoc model."""

    def test_valid_symbol(self):
        """Test creating valid Python symbol documentation."""
        symbol = PythonSymbolDoc(
            symbol_name="BaseModel",
            symbol_type="class",
            docstring="A base class for models",
            source_file=Path("pydantic/main.py"),
            line_number=100,
            parent_class=None,
        )
        assert symbol.symbol_name == "BaseModel"
        assert symbol.symbol_type == "class"
        assert symbol.line_number == 100

    def test_method_symbol(self):
        """Test method symbol with parent class."""
        symbol = PythonSymbolDoc(
            symbol_name="BaseModel.model_dump",
            symbol_type="method",
            docstring="Dump model to dict",
            source_file=Path("pydantic/main.py"),
            line_number=200,
            parent_class="BaseModel",
        )
        assert symbol.parent_class == "BaseModel"
        assert symbol.symbol_type == "method"


class TestRepoConfig:
    """Test RepoConfig model."""

    def test_pydantic_config(self):
        """Test pydantic repository configuration."""
        assert PYDANTIC_CONFIG.name == "pydantic"
        assert "pydantic/pydantic.git" in PYDANTIC_CONFIG.repo_url
        assert PYDANTIC_CONFIG.branch == "main"
        assert PYDANTIC_CONFIG.docs_path == Path("docs")
        assert PYDANTIC_CONFIG.source_path == Path("pydantic")

    def test_pydantic_ai_config(self):
        """Test pydantic-ai repository configuration."""
        assert PYDANTIC_AI_CONFIG.name == "pydantic_ai"
        assert "pydantic-ai.git" in PYDANTIC_AI_CONFIG.repo_url
        assert PYDANTIC_AI_CONFIG.branch == "main"


class TestCleanDocstring:
    """Test docstring cleaning functionality."""

    def test_remove_admonitions(self):
        """Test removal of markdown admonitions."""
        docstring = """
This is a docstring.

!!! note
    This is an admonition.
    It should be removed.

This should remain.
"""
        cleaned = clean_docstring(docstring)
        assert "!!! note" not in cleaned
        assert "This is an admonition" not in cleaned
        assert "This should remain" in cleaned

    def test_normalize_whitespace(self):
        """Test whitespace normalization."""
        docstring = "Line 1\n\n\n\n\n\nLine 2"
        cleaned = clean_docstring(docstring)
        # Should reduce excessive newlines
        assert "\n\n\n\n\n\n" not in cleaned

    def test_empty_docstring(self):
        """Test handling of empty docstring."""
        assert clean_docstring("") == ""
        assert clean_docstring(None) == ""


class TestChunkText:
    """Test text chunking functionality."""

    def test_short_text_no_chunking(self):
        """Test that short text is not chunked."""
        text = "Short text"
        chunks = chunk_text(text, max_tokens=1200)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_chunking(self):
        """Test chunking of long text."""
        # Create text with paragraph breaks that exceeds token limit
        paragraphs = ["This is paragraph number {}.\n\n".format(i) for i in range(50)]
        text = "".join(paragraphs)
        chunks = chunk_text(text, max_tokens=100)
        # Should create multiple chunks
        assert len(chunks) > 1
        # All chunks should be non-empty
        assert all(len(chunk) > 0 for chunk in chunks)

    def test_empty_text(self):
        """Test handling of empty text."""
        assert chunk_text("") == []
        assert chunk_text(None) == []

    def test_paragraph_boundaries(self):
        """Test that chunking respects paragraph boundaries."""
        text = "Para1\n\nPara2\n\nPara3\n\nPara4"
        chunks = chunk_text(text, max_tokens=50)
        # Should split at paragraph boundaries
        for chunk in chunks:
            assert not chunk.startswith("\n\n")


class TestBuildApiUrl:
    """Test API URL building."""

    def test_pydantic_url(self):
        """Test building Pydantic API URL."""
        url = build_api_url(
            "pydantic.BaseModel", "https://docs.pydantic.dev/latest"
        )
        assert "https://docs.pydantic.dev/latest/api/" in url
        assert "base-model" in url.lower() or "basemodel" in url.lower()

    def test_short_symbol(self):
        """Test URL for short symbol name."""
        url = build_api_url("BaseModel", "https://docs.pydantic.dev/latest")
        assert url.endswith("/api/")

    def test_url_formatting(self):
        """Test URL formatting (underscores to hyphens)."""
        url = build_api_url(
            "pydantic.base_model", "https://docs.pydantic.dev/latest"
        )
        assert "base-model" in url


class TestExtractHeadingInfo:
    """Test markdown heading extraction."""

    def test_h1_heading(self):
        """Test extracting H1 heading."""
        level, text, anchor = extract_heading_info("# Main Title")
        assert level == 1
        assert text == "Main Title"
        assert anchor == "main-title"

    def test_h2_heading(self):
        """Test extracting H2 heading."""
        level, text, anchor = extract_heading_info("## Subsection")
        assert level == 2
        assert text == "Subsection"
        assert anchor == "subsection"

    def test_non_heading(self):
        """Test non-heading line."""
        level, text, anchor = extract_heading_info("Just some text")
        assert level == 0
        assert text == ""
        assert anchor == ""

    def test_anchor_special_chars(self):
        """Test anchor generation with special characters."""
        level, text, anchor = extract_heading_info("## API Reference (v2.0)")
        assert level == 2
        assert anchor == "api-reference-v20"

    def test_anchor_whitespace(self):
        """Test anchor generation with multiple spaces."""
        level, text, anchor = extract_heading_info("## Multiple   Spaces")
        assert "-" in anchor
        assert "  " not in anchor


class TestJsonlFormatCompatibility:
    """Test JSONL format compatibility with existing system."""

    def test_jsonl_has_required_fields(self):
        """Test that JSONL output has all required fields."""
        chunk = DocumentChunk(
            title="Test",
            anchor="test",
            heading_level=1,
            md_text="Content",
            url="https://example.com",
            page="page",
            source_site="pydantic",
        )
        jsonl = chunk.to_jsonl()

        # Check all required fields are present
        required_fields = [
            "title",
            "anchor",
            "heading_level",
            "md_text",
            "url",
            "page",
            "source_site",
        ]
        for field in required_fields:
            assert field in jsonl, f"Missing required field: {field}"

    def test_jsonl_serializable(self):
        """Test that JSONL output can be serialized to JSON."""
        chunk = DocumentChunk(
            title="Test",
            anchor=None,
            heading_level=0,
            md_text="Content",
            url="https://example.com",
            page="page",
            source_site="pydantic",
        )
        jsonl = chunk.to_jsonl()

        # Should be JSON serializable
        json_str = json.dumps(jsonl)
        assert isinstance(json_str, str)

        # Should be deserializable
        parsed = json.loads(json_str)
        assert parsed["title"] == "Test"


class TestNoFormattingArtifacts:
    """Test that extraction produces clean text without formatting artifacts."""

    def test_clean_text_no_line_numbers(self):
        """Test that text doesn't contain line number artifacts."""
        # Simulate checking extracted text
        sample_text = "This is clean text without line numbers like 46 or 147."
        # Should not match the line number pattern: \d{2,}\n\n
        import re

        pattern = r"\d{2,}\n\n"
        matches = re.findall(pattern, sample_text)
        assert len(matches) == 0

    def test_no_excessive_newlines(self):
        """Test that text doesn't have excessive newlines."""
        docstring = "Line 1\n\n\n\n\n\nLine 2"
        cleaned = clean_docstring(docstring)
        # Should not have more than 3 consecutive newlines
        assert "\n\n\n\n" not in cleaned

    def test_no_html_table_artifacts(self):
        """Test that markdown doesn't contain HTML table artifacts."""
        # Clean markdown should not have patterns like: n\n\n\nbool\n | None\n\n\n
        sample = "This is | a table | with pipes"
        # The old HTML parser would create artifacts, new extractor shouldn't
        assert "n\n\n\nbool\n | None\n\n\n" not in sample

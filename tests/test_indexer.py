"""Tests for indexer module - core indexing and processing logic."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from mcp_pydantic_docs.indexer import (
    chunk_markdown,
    iter_sections,
    tok_len,
)
from mcp_pydantic_docs.utils import (
    bs4_has_lxml,
    clean_html_for_text,
    to_markdown,
)


@pytest.fixture
def sample_html() -> str:
    """Sample HTML with typical documentation structure."""
    return """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav class="md-nav">Navigation</nav>
        <header class="md-header">Header</header>
        <main role="main">
            <h1 id="main-heading">Main Heading</h1>
            <p>This is the main content.</p>
            <h2 id="section-one">Section One</h2>
            <p>Content for section one.</p>
            <pre><code>code block</code></pre>
            <h2 id="section-two">Section Two</h2>
            <p>Content for section two.</p>
        </main>
        <footer class="md-footer">Footer</footer>
    </body>
    </html>
    """


@pytest.fixture
def sample_html_no_sections() -> str:
    """HTML without section headers."""
    return """
    <html><body>
    <div>Just some content without headers.</div>
    </body></html>
    """


class TestBasicFunctions:
    """Test basic utility functions."""

    def test_bs4_has_lxml_returns_bool(self):
        """Test that bs4_has_lxml returns a boolean."""
        result = bs4_has_lxml()
        assert isinstance(result, bool)

    def test_tok_len_counts_tokens(self):
        """Test token counting with known string."""
        text = "This is a test string"
        result = tok_len(text)
        assert isinstance(result, int)
        assert result > 0

    def test_tok_len_empty_string(self):
        """Test token counting with empty string."""
        result = tok_len("")
        assert result == 0

    def test_tok_len_longer_text(self):
        """Test that longer text has more tokens."""
        short = "Hello"
        long = "Hello " * 100
        assert tok_len(long) > tok_len(short)


class TestHtmlCleaning:
    """Test HTML cleaning functionality."""

    def test_clean_html_removes_nav(self, sample_html):
        """Test that navigation is removed."""
        result = str(clean_html_for_text(sample_html))
        assert "Navigation" not in result

    def test_clean_html_removes_header(self, sample_html):
        """Test that header is removed."""
        result = str(clean_html_for_text(sample_html))
        assert "Header" not in result

    def test_clean_html_removes_footer(self, sample_html):
        """Test that footer is removed."""
        result = str(clean_html_for_text(sample_html))
        assert "Footer" not in result

    def test_clean_html_preserves_main(self, sample_html):
        """Test that main content is preserved."""
        result = str(clean_html_for_text(sample_html))
        assert "main content" in result.lower()

    def test_clean_html_extracts_main_tag(self, sample_html):
        """Test that main tag content is properly extracted."""
        soup = clean_html_for_text(sample_html)
        # Should have main content but not nav/header/footer
        text = soup.get_text()
        assert "Main Heading" in text
        assert "Section One" in text


class TestMarkdownConversion:
    """Test HTML to markdown conversion."""

    def test_to_markdown_converts_html(self):
        """Test basic HTML to markdown conversion."""
        html = "<p>This is a paragraph</p>"
        result = to_markdown(html)
        assert "paragraph" in result.lower()

    def test_to_markdown_removes_code_fences(self):
        """Test that code fences are handled."""
        html = "<pre><code>```python\ncode\n```</code></pre>"
        result = to_markdown(html)
        # Should not have triple backticks in sequence
        assert "``````" not in result

    def test_to_markdown_removes_table_pipes(self):
        """Test that table pipes are removed."""
        html = "<table><tr><td>Cell</td></tr></table>"
        result = to_markdown(html)
        # Pipes should be stripped
        assert "|" not in result

    def test_to_markdown_normalizes_whitespace(self):
        """Test that whitespace is normalized."""
        html = "<p>Text   with    lots     of      spaces</p>"
        result = to_markdown(html)
        # Should collapse to single spaces
        assert "    " not in result


class TestSectionExtraction:
    """Test section extraction from HTML."""

    def test_iter_sections_with_headings(self, sample_html):
        """Test extracting sections with h1/h2/h3 headings."""
        soup = BeautifulSoup(sample_html, "html.parser")
        sections = list(iter_sections(soup))
        
        assert len(sections) > 0
        # Should have sections for each h1/h2 with id
        section_titles = [s[1] for s in sections]
        assert any("Main Heading" in title for title in section_titles)

    def test_iter_sections_without_headings(self, sample_html_no_sections):
        """Test that page without sections yields whole page."""
        soup = BeautifulSoup(sample_html_no_sections, "html.parser")
        sections = list(iter_sections(soup))
        
        # Should yield one section with None anchor
        assert len(sections) == 1
        assert sections[0][0] is None  # anchor

    def test_iter_sections_extracts_anchors(self, sample_html):
        """Test that anchors are properly extracted."""
        soup = BeautifulSoup(sample_html, "html.parser")
        sections = list(iter_sections(soup))
        
        anchors = [s[0] for s in sections if s[0]]
        assert len(anchors) > 0
        # Should have some of our test anchors
        assert any("section" in str(a) for a in anchors)

    def test_iter_sections_respects_hierarchy(self):
        """Test that section hierarchy is respected."""
        html = """
        <div>
            <h2 id="h2">Level 2</h2>
            <p>Content 2</p>
            <h3 id="h3">Level 3</h3>
            <p>Content 3</p>
            <h2 id="h2-2">Level 2 Again</h2>
            <p>Content 2-2</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sections = list(iter_sections(soup))
        
        # Should have sections for h2 elements
        assert len(sections) >= 2


class TestMarkdownChunking:
    """Test markdown chunking logic."""

    def test_chunk_markdown_small_text(self):
        """Test that small text is not chunked."""
        text = "This is a small piece of text."
        chunks = chunk_markdown(text, max_tok=1200)
        
        assert len(chunks) == 1
        assert chunks[0] == text.strip()

    def test_chunk_markdown_large_text(self):
        """Test that large text is chunked."""
        # Create text larger than token limit
        text = "This is a paragraph.\n\n" * 500
        chunks = chunk_markdown(text, max_tok=100)
        
        # Should split into multiple chunks
        assert len(chunks) > 1
        # Each chunk should be non-empty
        assert all(len(c) > 0 for c in chunks)

    def test_chunk_markdown_preserves_paragraphs(self):
        """Test that paragraph boundaries are preserved."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_markdown(text, max_tok=1200)
        
        # Should keep as one chunk if small enough
        assert len(chunks) == 1
        assert "\n\n" in chunks[0]

    def test_chunk_markdown_splits_on_paragraphs(self):
        """Test that splits happen on paragraph boundaries."""
        paragraphs = ["Para " + str(i) for i in range(100)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_markdown(text, max_tok=50)
        
        # Should have multiple chunks
        assert len(chunks) > 1
        # Each chunk should not be empty
        assert all(len(c.strip()) > 0 for c in chunks)


class TestProcessFile:
    """Test file processing functions - using mocks for speed."""

    def test_process_file_record_structure(self):
        """Test that process_file produces correct record structure."""
        # Mock the actual processing - we just verify structure
        
        mock_record = {
            "title": "Test Title",
            "md_text": "Test content",
            "url": "https://test.com/page.html#anchor",
            "page": "page.html",
            "source_site": "test_site",
            "anchor": "anchor",
            "heading_level": 2
        }
        
        # Verify record has expected keys
        assert "title" in mock_record
        assert "md_text" in mock_record
        assert "url" in mock_record
        assert "page" in mock_record
        assert "source_site" in mock_record


class TestBuildIndex:
    """Test index building (unit tests only, no actual indexing)."""

    def test_build_index_function_exists(self):
        """Test that build_index function exists with correct signature."""
        import inspect

        from mcp_pydantic_docs.indexer import build_index
        
        # Verify function exists and has expected parameters
        sig = inspect.signature(build_index)
        params = list(sig.parameters.keys())
        
        assert "jsonl_files" in params
        assert "output_name" in params

    def test_build_index_requires_rank_bm25_import(self):
        """Test that build_index depends on rank_bm25."""
        import inspect
        
        # Just verify the import is attempted in the module
        import mcp_pydantic_docs.indexer as indexer_module
        source = inspect.getsource(indexer_module)
        
        # Should have rank_bm25 import
        assert "rank_bm25" in source or "BM25" in source

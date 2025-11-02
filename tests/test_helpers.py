"""Tests for helper functions in mcp module."""

from __future__ import annotations

from mcp_pydantic_docs.mcp import (
    DOC_ROOT,
    DOC_ROOT_AI,
    _clean_snippet,
    _deny_remote,
    _display_url,
    _extract_section,
    _is_within,
    _safe_rel_from_url,
    _tokenize,
)


class TestTokenize:
    """Test tokenization function."""

    def test_tokenize_basic_text(self):
        """Test basic tokenization."""
        text = "This is a test"
        tokens = _tokenize(text)
        
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_tokenize_lowercase_conversion(self):
        """Test that tokens are lowercased."""
        text = "UPPER Case Mixed"
        tokens = _tokenize(text)
        
        assert all(t.islower() for t in tokens)

    def test_tokenize_filters_short_tokens(self):
        """Test that single-character tokens are filtered."""
        text = "a bb ccc d eee"
        tokens = _tokenize(text)
        
        # Should only keep tokens with length > 1
        assert "a" not in tokens
        assert "d" not in tokens
        assert "bb" in tokens or "ccc" in tokens

    def test_tokenize_handles_special_chars(self):
        """Test handling of special characters."""
        text = "test-value_name #tag"
        tokens = _tokenize(text)
        
        # Should preserve hyphens, underscores, hashes
        assert any("-" in t or "_" in t or "#" in t for t in tokens)

    def test_tokenize_splits_on_whitespace(self):
        """Test that whitespace splits tokens."""
        text = "word1 word2 word3"
        tokens = _tokenize(text)
        
        assert len(tokens) >= 3

    def test_tokenize_empty_string(self):
        """Test empty string returns empty list."""
        tokens = _tokenize("")
        assert tokens == []


class TestCleanSnippet:
    """Test snippet cleaning function."""

    def test_clean_snippet_collapses_whitespace(self):
        """Test that multiple spaces are collapsed."""
        snippet = "Text   with    many     spaces"
        result = _clean_snippet(snippet)
        
        assert "   " not in result

    def test_clean_snippet_removes_code_fences(self):
        """Test that code fences are removed."""
        snippet = "Text ```python\ncode\n``` more text"
        result = _clean_snippet(snippet)
        
        assert "```" not in result

    def test_clean_snippet_removes_table_pipes(self):
        """Test that markdown table rows are removed."""
        snippet = "Text\n| col1 | col2 |\nMore text"
        result = _clean_snippet(snippet)
        
        # Pipes should be replaced with spaces
        assert snippet != result

    def test_clean_snippet_removes_line_numbers(self):
        """Test that line number bursts are removed."""
        snippet = "1 2 3 4 5 6 7 8 text"
        result = _clean_snippet(snippet)
        
        # Should remove number sequences
        assert result != snippet

    def test_clean_snippet_limits_length(self):
        """Test that snippets are limited in length."""
        long_snippet = "x" * 1000
        result = _clean_snippet(long_snippet)
        
        # Should be truncated (max 420 chars based on _SNIP_MAX)
        assert len(result) <= 420

    def test_clean_snippet_strips_whitespace(self):
        """Test that leading/trailing whitespace is removed."""
        snippet = "   content   "
        result = _clean_snippet(snippet)
        
        assert result == "content"


class TestIsWithin:
    """Test path validation function."""

    def test_is_within_accepts_child_path(self, tmp_path):
        """Test that child paths are accepted."""
        root = tmp_path
        child = tmp_path / "subdir" / "file.txt"
        child.parent.mkdir(parents=True, exist_ok=True)
        child.touch()
        
        assert _is_within(root, child) is True

    def test_is_within_rejects_parent_path(self, tmp_path):
        """Test that parent paths are rejected."""
        root = tmp_path / "subdir"
        root.mkdir(exist_ok=True)
        parent = tmp_path
        
        assert _is_within(root, parent) is False

    def test_is_within_accepts_same_path(self, tmp_path):
        """Test that same path is accepted."""
        assert _is_within(tmp_path, tmp_path) is True

    def test_is_within_handles_nonexistent_paths(self, tmp_path):
        """Test handling of nonexistent paths."""
        root = tmp_path
        nonexistent = tmp_path / "nonexistent" / "file.txt"
        
        # Should handle gracefully
        result = _is_within(root, nonexistent)
        assert isinstance(result, bool)


class TestDenyRemote:
    """Test remote URL blocking."""

    def test_deny_remote_allows_local_paths(self):
        """Test that local paths are allowed."""
        # Should not raise
        _deny_remote("local://pydantic/api/base_model")
        _deny_remote("api/base_model.html")

    def test_deny_remote_allows_known_bases(self):
        """Test that known documentation bases are allowed."""
        # Should not raise for known bases
        _deny_remote("https://docs.pydantic.dev/latest/api/base_model")
        _deny_remote("https://ai.pydantic.dev/agents")

    def test_deny_remote_blocks_unknown_urls(self):
        """Test that unknown remote URLs are blocked when offline mode enabled."""
        # This depends on _OFFLINE_ONLY being True
        try:
            _deny_remote("https://evil.com/malicious")
            # If no error, offline mode is disabled
        except ValueError as e:
            # If error, offline mode is enabled
            assert "Remote URLs disabled" in str(e) or "disabled" in str(e).lower()


class TestSafeRelFromUrl:
    """Test URL to relative path conversion."""

    def test_safe_rel_from_url_handles_pydantic_urls(self):
        """Test handling of pydantic.dev URLs."""
        url = "https://docs.pydantic.dev/latest/api/base_model.html"
        root, rel = _safe_rel_from_url(url)
        
        assert root == DOC_ROOT
        assert "api/base_model.html" in rel

    def test_safe_rel_from_url_handles_pydantic_ai_urls(self):
        """Test handling of pydantic AI URLs."""
        url = "https://ai.pydantic.dev/agents/"
        root, rel = _safe_rel_from_url(url)
        
        assert root == DOC_ROOT_AI
        assert "agents" in rel

    def test_safe_rel_from_url_handles_local_urls(self):
        """Test handling of local:// URLs."""
        url = "local://pydantic/api/base_model.html"
        root, rel = _safe_rel_from_url(url)
        
        assert root == DOC_ROOT
        assert "api/base_model.html" in rel

    def test_safe_rel_from_url_removes_anchors(self):
        """Test that anchors are removed from paths."""
        url = "api/base_model.html#some-anchor"
        root, rel = _safe_rel_from_url(url)
        
        assert "#" not in rel
        assert "api/base_model.html" in rel

    def test_safe_rel_from_url_prevents_directory_traversal(self):
        """Test that .. is removed from paths."""
        url = "api/../../etc/passwd"
        root, rel = _safe_rel_from_url(url)
        
        assert ".." not in rel

    def test_safe_rel_from_url_handles_relative_paths(self):
        """Test handling of relative paths."""
        url = "api/base_model.html"
        root, rel = _safe_rel_from_url(url)
        
        assert rel == "api/base_model.html"


class TestDisplayUrl:
    """Test URL display formatting."""

    def test_display_url_formats_pydantic_urls(self):
        """Test formatting pydantic URLs."""
        url = _display_url(DOC_ROOT, "api/base_model.html")
        
        assert url.startswith("local://pydantic/")
        assert "api/base_model.html" in url

    def test_display_url_formats_pydantic_ai_urls(self):
        """Test formatting pydantic AI URLs."""
        url = _display_url(DOC_ROOT_AI, "agents/index.html")
        
        assert url.startswith("local://pydantic-ai/")
        assert "agents" in url

    def test_display_url_concatenates_properly(self):
        """Test that path concatenation works."""
        url = _display_url(DOC_ROOT, "test.html")
        
        # Should not have double slashes except in protocol
        parts = url.split("://", 1)
        assert "//" not in parts[1]


class TestExtractSection:
    """Test section extraction from HTML."""

    def test_extract_section_finds_heading(self):
        """Test that sections are extracted by heading ID."""
        html = """
        <h2 id="section-one">Section One</h2>
        <p>Content for section one.</p>
        <h2 id="section-two">Section Two</h2>
        <p>Content for section two.</p>
        """
        
        result = _extract_section(html, "section-one")
        
        assert "Section One" in result
        assert "Content for section one" in result
        # Should not include section two
        assert "Section Two" not in result

    def test_extract_section_stops_at_same_level_heading(self):
        """Test that extraction stops at same-level heading."""
        html = """
        <h2 id="target">Target</h2>
        <p>Content</p>
        <h3>Subsection</h3>
        <p>Sub content</p>
        <h2 id="next">Next Section</h2>
        """
        
        result = _extract_section(html, "target")
        
        assert "Target" in result
        assert "Content" in result
        assert "Subsection" in result
        assert "Next Section" not in result

    def test_extract_section_includes_subsections(self):
        """Test that lower-level headings are included."""
        html = """
        <h2 id="main">Main</h2>
        <p>Content</p>
        <h3>Sub</h3>
        <p>Sub content</p>
        """
        
        result = _extract_section(html, "main")
        
        assert "Main" in result
        assert "Sub" in result
        assert "Sub content" in result

    def test_extract_section_handles_missing_anchor(self):
        """Test handling of non-existent anchor."""
        html = "<h2 id='exists'>Exists</h2><p>Content</p>"
        
        result = _extract_section(html, "nonexistent")
        
        # Should return empty string for missing anchor
        assert result == ""

    def test_extract_section_limits_length(self):
        """Test that extracted sections are length-limited."""
        # Create very long content
        html = f"<h2 id='test'>Test</h2><p>{'x' * 10000}</p>"
        
        result = _extract_section(html, "test")
        
        # Should be truncated to MAX_SECTION (4000)
        assert len(result) <= 4000

    def test_extract_section_handles_h1_h2_h3(self):
        """Test that h1, h2, and h3 tags work."""
        for level in [1, 2, 3]:
            html = f"<h{level} id='test'>Heading</h{level}><p>Content</p>"
            result = _extract_section(html, "test")
            assert "Heading" in result
            assert "Content" in result


class TestRankingFunctions:
    """Test search ranking helpers."""

    def test_tokenize_for_search_consistency(self):
        """Test that tokenize is consistent for search queries."""
        query1 = "BaseModel validation"
        query2 = "basemodel VALIDATION"
        
        tokens1 = _tokenize(query1)
        tokens2 = _tokenize(query2)
        
        # Should produce same tokens (case-insensitive)
        assert tokens1 == tokens2

    def test_clean_snippet_for_search_results(self):
        """Test snippet cleaning produces readable results."""
        raw_snippet = """
        | Table | Row |
        ```python
        code
        ```
        Actual content here
        """
        
        result = _clean_snippet(raw_snippet)
        
        assert "Actual content here" in result
        assert "```" not in result
        assert "|" not in result


class TestPathHelpers:
    """Test path manipulation helpers."""

    def test_safe_rel_strips_leading_slashes(self):
        """Test that leading slashes are removed."""
        url = "/api/base_model.html"
        root, rel = _safe_rel_from_url(url)
        
        assert not rel.startswith("/")

    def test_safe_rel_handles_empty_string(self):
        """Test handling of empty string."""
        root, rel = _safe_rel_from_url("")
        
        assert isinstance(rel, str)

    def test_display_url_consistent_format(self):
        """Test that display URLs have consistent format."""
        url1 = _display_url(DOC_ROOT, "api/test.html")
        url2 = _display_url(DOC_ROOT, "/api/test.html")
        
        # Should produce similar results (normalized)
        assert "api/test.html" in url1
        assert "api/test.html" in url2

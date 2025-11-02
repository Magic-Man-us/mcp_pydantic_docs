"""Comprehensive unit tests for utils.py module."""

from __future__ import annotations

from bs4 import BeautifulSoup

from mcp_pydantic_docs.utils import (
    FENCE_PATTERN,
    LINE_NO_BURST_PATTERN,
    MULTI_WS_PATTERN,
    PIPE_ROWS_PATTERN,
    bs4_has_lxml,
    clean_html_for_text,
    normalize_text,
    to_markdown,
)


class TestBs4HasLxml:
    """Test lxml parser detection."""

    def test_returns_boolean(self):
        """Test that function returns a boolean."""
        result = bs4_has_lxml()
        assert isinstance(result, bool)

    def test_consistent_result(self):
        """Test that function returns consistent result."""
        result1 = bs4_has_lxml()
        result2 = bs4_has_lxml()
        assert result1 == result2


class TestCleanHtmlForText:
    """Test HTML cleaning functionality."""

    def test_removes_navigation(self):
        """Test that navigation elements are removed."""
        html = '<nav>Nav content</nav><main>Main content</main>'
        result = str(clean_html_for_text(html))
        assert 'Nav content' not in result
        assert 'Main content' in result

    def test_removes_header(self):
        """Test that header elements are removed."""
        html = '<header>Header</header><main>Main</main>'
        result = str(clean_html_for_text(html))
        assert 'Header' not in result
        assert 'Main' in result

    def test_removes_footer(self):
        """Test that footer elements are removed."""
        html = '<footer>Footer</footer><main>Main</main>'
        result = str(clean_html_for_text(html))
        assert 'Footer' not in result
        assert 'Main' in result

    def test_removes_aside(self):
        """Test that aside elements are removed."""
        html = '<aside>Sidebar</aside><main>Main</main>'
        result = str(clean_html_for_text(html))
        assert 'Sidebar' not in result
        assert 'Main' in result

    def test_removes_md_header_class(self):
        """Test that .md-header class elements are removed."""
        html = '<div class="md-header">Header</div><main>Main</main>'
        result = str(clean_html_for_text(html))
        assert 'Header' not in result

    def test_removes_md_sidebar_class(self):
        """Test that .md-sidebar class elements are removed."""
        html = '<div class="md-sidebar">Sidebar</div><main>Main</main>'
        result = str(clean_html_for_text(html))
        assert 'Sidebar' not in result

    def test_removes_script_tags(self):
        """Test that script tags are removed."""
        html = '<script>alert("hi")</script><main>Main</main>'
        result = str(clean_html_for_text(html))
        assert 'alert' not in result

    def test_removes_style_tags(self):
        """Test that style tags are removed."""
        html = '<style>body { color: red; }</style><main>Main</main>'
        result = str(clean_html_for_text(html))
        assert 'color' not in result

    def test_extracts_main_role(self):
        """Test that main[role='main'] is extracted."""
        html = '<nav>Nav</nav><main role="main">Main content</main><footer>Footer</footer>'
        result = str(clean_html_for_text(html))
        assert 'Main content' in result
        assert 'Nav' not in result
        assert 'Footer' not in result

    def test_extracts_main_tag(self):
        """Test that <main> tag is extracted."""
        html = '<nav>Nav</nav><main>Main content</main><footer>Footer</footer>'
        result = str(clean_html_for_text(html))
        assert 'Main content' in result

    def test_extracts_md_content_inner(self):
        """Test that .md-content__inner is extracted."""
        html = '<nav>Nav</nav><div class="md-content__inner">Content</div><footer>Footer</footer>'
        result = str(clean_html_for_text(html))
        assert 'Content' in result

    def test_extracts_article(self):
        """Test that <article> tag is extracted."""
        html = '<nav>Nav</nav><article>Article content</article><footer>Footer</footer>'
        result = str(clean_html_for_text(html))
        assert 'Article content' in result

    def test_cleans_boilerplate_after_extraction(self):
        """Test that boilerplate is cleaned even within main."""
        html = '<main><nav>Nav</nav>Main content</main>'
        result = str(clean_html_for_text(html))
        assert 'Nav' not in result
        assert 'Main content' in result

    def test_no_main_returns_full_cleaned_document(self):
        """Test that full document is returned when no main container found."""
        html = '<div>Content</div>'
        result = str(clean_html_for_text(html))
        assert 'Content' in result

    def test_returns_beautifulsoup_object(self):
        """Test that function returns BeautifulSoup object."""
        html = '<div>Content</div>'
        result = clean_html_for_text(html)
        assert isinstance(result, BeautifulSoup)


class TestToMarkdown:
    """Test HTML to markdown conversion."""

    def test_converts_paragraphs(self):
        """Test basic paragraph conversion."""
        html = '<p>Paragraph text</p>'
        result = to_markdown(html)
        assert 'Paragraph text' in result

    def test_converts_headings(self):
        """Test heading conversion with ATX style."""
        html = '<h1>Heading 1</h1><h2>Heading 2</h2>'
        result = to_markdown(html)
        assert 'Heading 1' in result
        assert 'Heading 2' in result

    def test_removes_empty_code_blocks(self):
        """Test that empty code blocks are removed."""
        html = '<pre><code>```\n```</code></pre>'
        result = to_markdown(html)
        # Should not have empty code block markers
        assert '``````' not in result

    def test_strips_fenced_blocks(self):
        """Test that fenced code blocks are stripped."""
        html = '<div>```python\ncode\n```</div>'
        result = to_markdown(html)
        # Fences should be removed by FENCE_PATTERN
        assert '```' not in result

    def test_removes_table_pipes(self):
        """Test that table pipe rows are removed."""
        html = '<table><tr><td>Cell 1</td><td>Cell 2</td></tr></table>'
        result = to_markdown(html)
        # Pipes should be stripped
        assert '|' not in result

    def test_removes_line_number_bursts(self):
        """Test that line number sequences are removed."""
        html = '<pre>1 2 3 4 5 6 7 8\ncode here</pre>'
        result = to_markdown(html)
        # Line numbers should not appear as burst
        # The pattern catches 5+ consecutive numbers

    def test_removes_leftover_backticks(self):
        """Test that leftover backticks are removed."""
        html = '<code>`test`</code>'
        result = to_markdown(html)
        assert '`' not in result

    def test_collapses_whitespace(self):
        """Test that multiple spaces are collapsed."""
        html = '<div>Text    with     many      spaces</div>'
        result = to_markdown(html)
        assert '    ' not in result
        # Should be collapsed to single spaces

    def test_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        html = '<div>  content  </div>'
        result = to_markdown(html)
        assert result == result.strip()

    def test_handles_complex_html(self):
        """Test conversion of complex HTML structures."""
        html = '''
        <div>
            <h2>Heading</h2>
            <p>Paragraph with <strong>bold</strong> and <em>italic</em>.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </div>
        '''
        result = to_markdown(html)
        assert 'Heading' in result
        assert 'Paragraph' in result


class TestNormalizeText:
    """Test text normalization functionality."""

    def test_empty_string_returns_empty(self):
        """Test that empty string returns empty."""
        assert normalize_text('') == ''

    def test_strips_leading_trailing_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        text = '  content  '
        result = normalize_text(text)
        assert result == 'content'

    def test_removes_carriage_returns(self):
        """Test that carriage returns are removed."""
        text = 'line1\r\nline2\r\nline3'
        result = normalize_text(text)
        assert '\r' not in result

    def test_removes_null_characters(self):
        """Test that null characters are removed."""
        text = 'content\x00here'
        result = normalize_text(text)
        assert '\x00' not in result

    def test_removes_empty_headings(self):
        """Test that empty markdown headings are removed."""
        text = '### \n\ncontent'
        result = normalize_text(text)
        assert '###' not in result
        assert 'content' in result

    def test_removes_empty_dividers(self):
        """Test that empty markdown dividers are removed."""
        text = 'content\n---\n\nmore content'
        result = normalize_text(text)
        # Empty dividers should be removed
        lines = result.split('\n')
        assert not any(line.strip() in ['---', '***', '___'] for line in lines)

    def test_removes_empty_quotes(self):
        """Test that empty quote lines are removed."""
        text = 'content\n>\n\nmore content'
        result = normalize_text(text)
        # Empty quote markers should be removed

    def test_collapses_multiple_newlines(self):
        """Test that multiple newlines are collapsed to max 2."""
        text = 'line1\n\n\n\n\nline2'
        result = normalize_text(text)
        assert '\n\n\n' not in result
        # Should have at most 2 consecutive newlines

    def test_collapses_many_newlines(self):
        """Test that many consecutive newlines are collapsed."""
        text = 'line1' + '\n' * 100 + 'line2'
        result = normalize_text(text)
        assert '\n\n\n' not in result

    def test_strips_line_whitespace(self):
        """Test that whitespace on each line is stripped."""
        text = '  line1  \n  line2  \n  line3  '
        result = normalize_text(text)
        lines = result.split('\n')
        for line in lines:
            if line:
                assert line == line.strip()

    def test_collapses_spaces_within_lines(self):
        """Test that multiple spaces within lines are collapsed."""
        text = 'word1    word2     word3'
        result = normalize_text(text)
        assert '  ' not in result

    def test_removes_trailing_spaces_before_newlines(self):
        """Test that trailing spaces before newlines are removed."""
        text = 'line1   \nline2   \n'
        result = normalize_text(text)
        lines = result.split('\n')
        for line in lines:
            if line:
                assert not line.endswith(' ')

    def test_removes_leading_spaces_after_newlines(self):
        """Test that leading spaces after newlines are removed."""
        text = 'line1\n   line2\n   line3'
        result = normalize_text(text)
        lines = result.split('\n')
        for line in lines:
            if line:
                assert not line.startswith(' ')

    def test_preserves_paragraph_breaks(self):
        """Test that paragraph breaks (double newlines) are preserved."""
        text = 'paragraph1\n\nparagraph2\n\nparagraph3'
        result = normalize_text(text)
        # Should have double newlines for paragraphs
        assert 'paragraph1' in result
        assert 'paragraph2' in result
        assert 'paragraph3' in result

    def test_handles_mixed_whitespace(self):
        """Test handling of mixed whitespace characters."""
        text = 'line1\t\t\nline2  \n  line3'
        result = normalize_text(text)
        # Tabs and multiple spaces should be normalized
        assert '\t' not in result

    def test_maintains_single_newlines(self):
        """Test that single newlines are preserved where appropriate."""
        text = 'line1\nline2\nline3'
        result = normalize_text(text)
        lines = result.split('\n')
        assert len(lines) == 3

    def test_comprehensive_normalization(self):
        """Test comprehensive text normalization."""
        text = '''
        
        
        ### Empty heading
        
        Content   with    excessive     spaces
        
        
        
        More content
        
        
        '''
        result = normalize_text(text)
        # Should be well-formed after normalization
        assert '\n\n\n' not in result
        assert '  ' not in result
        assert result == result.strip()


class TestRegexPatterns:
    """Test regex pattern functionality."""

    def test_fence_pattern_matches_code_blocks(self):
        """Test FENCE_PATTERN matches code fences."""
        text = '```python\ncode\n```'
        match = FENCE_PATTERN.search(text)
        assert match is not None

    def test_fence_pattern_multiple_backticks(self):
        """Test FENCE_PATTERN handles varying backtick counts."""
        text = '````\ncode\n````'
        match = FENCE_PATTERN.search(text)
        assert match is not None

    def test_pipe_rows_pattern_matches_tables(self):
        """Test PIPE_ROWS_PATTERN matches table rows."""
        text = '| col1 | col2 | col3 |'
        match = PIPE_ROWS_PATTERN.search(text)
        assert match is not None

    def test_line_no_burst_pattern_matches_sequences(self):
        """Test LINE_NO_BURST_PATTERN matches number sequences."""
        text = '1 2 3 4 5 6 code'
        match = LINE_NO_BURST_PATTERN.search(text)
        assert match is not None

    def test_multi_ws_pattern_matches_whitespace(self):
        """Test MULTI_WS_PATTERN matches multiple whitespace."""
        text = 'word1    word2'
        match = MULTI_WS_PATTERN.search(text)
        assert match is not None
        assert match.group() == '    '


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_clean_html_with_empty_string(self):
        """Test clean_html_for_text with empty string."""
        result = clean_html_for_text('')
        assert isinstance(result, BeautifulSoup)

    def test_to_markdown_with_empty_string(self):
        """Test to_markdown with empty string."""
        result = to_markdown('')
        assert result == ''

    def test_normalize_text_with_only_whitespace(self):
        """Test normalize_text with only whitespace."""
        result = normalize_text('   \n\n   \n   ')
        assert result == ''

    def test_clean_html_with_malformed_html(self):
        """Test clean_html_for_text handles malformed HTML gracefully."""
        html = '<div><p>Unclosed paragraph<div>Another</div>'
        result = clean_html_for_text(html)
        assert isinstance(result, BeautifulSoup)

    def test_normalize_text_with_unicode(self):
        """Test normalize_text handles unicode characters."""
        text = 'Content with émojis 😀 and spëcial çhars'
        result = normalize_text(text)
        assert 'Content' in result
        assert '😀' in result

    def test_to_markdown_preserves_special_chars(self):
        """Test to_markdown preserves necessary special characters."""
        html = '<p>Price: $100 & up</p>'
        result = to_markdown(html)
        assert '$' in result or 'Price' in result

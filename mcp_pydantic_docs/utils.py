# src/mcp_pydantic_docs/utils.py
"""Shared utility functions for HTML parsing, text processing, and markdown conversion."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup
from bs4.element import Tag
from markdownify import markdownify as md


# ---- BeautifulSoup parser detection ----
def bs4_has_lxml() -> bool:
    """Check if lxml parser is available for BeautifulSoup."""
    try:
        import lxml  # noqa: F401
        return True
    except Exception:
        return False


# ---- HTML boilerplate removal selectors ----
MAIN_SELECTORS = [
    "main[role='main']",
    "main",
    "div.md-content__inner",
    "div.md-content",
    "div.md-main__inner",
    "article",
    "div.md-typeset",
]

REMOVE_SELECTORS = [
    "nav",
    "header",
    "footer",
    "aside",
    ".md-header",
    ".md-sidebar",
    ".md-nav",
    ".md-footer",
    ".md-search",
    ".md-search__overlay",
    ".md-tabs",
    ".skip-link",
    ".sr-only",
    ".visually-hidden",
    "script",
    "style",
]


# ---- Regex patterns for text cleaning ----
FENCE_PATTERN = re.compile(r"`{3,}.*?`{3,}", re.S)
PIPE_ROWS_PATTERN = re.compile(r"^\s*\|.*\|\s*$", re.M)
LINE_NO_BURST_PATTERN = re.compile(r"(?:^|\s)(?:\d{1,4}\s+){5,}\d{1,4}(?=\s|$)")
MULTI_WS_PATTERN = re.compile(r"\s+")


# ---- HTML processing ----
def clean_html_for_text(html: str) -> BeautifulSoup:
    """
    Remove navigation, headers, footers, and extract main content from HTML.
    
    Args:
        html: Raw HTML string
        
    Returns:
        BeautifulSoup object with cleaned content
    """
    soup = BeautifulSoup(html, "lxml" if bs4_has_lxml() else "html.parser")
    
    # Remove boilerplate elements
    for sel in REMOVE_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    
    # Try to find main content container
    main: Tag | None = None
    for sel in MAIN_SELECTORS:
        m = soup.select_one(sel)
        if isinstance(m, Tag):
            main = m
            break
    
    # If we found a main container, use only that
    if main is not None:
        soup = BeautifulSoup(str(main), "lxml" if bs4_has_lxml() else "html.parser")
        # Clean again in case there's nested boilerplate
        for sel in REMOVE_SELECTORS:
            for el in soup.select(sel):
                el.decompose()
    
    return soup


# ---- Markdown conversion ----
def to_markdown(html_fragment: str) -> str:
    """
    Convert HTML fragment to cleaned markdown text.
    
    Strips code fences, table rows, line numbers, and excessive whitespace.
    
    Args:
        html_fragment: HTML string to convert
        
    Returns:
        Cleaned markdown string
    """
    # Convert to markdown
    m = md(html_fragment, heading_style="ATX")
    
    # Remove empty code blocks
    m = re.sub(r"```(\s*)\n```", "", m)
    
    # Strip fenced blocks, table rows, and line number bursts
    m = FENCE_PATTERN.sub(" ", m)
    m = PIPE_ROWS_PATTERN.sub(" ", m)
    m = LINE_NO_BURST_PATTERN.sub(" ", m)
    
    # Remove leftover markdown formatting characters
    m = m.replace("|", " ").replace("`", " ")
    
    # Collapse whitespace
    m = MULTI_WS_PATTERN.sub(" ", m).strip()
    
    return m


# ---- Text normalization ----
def normalize_text(text: str) -> str:
    """
    Aggressively normalize text to remove excessive whitespace and newlines.
    
    This function:
    - Removes carriage returns and control characters
    - Removes empty markdown artifacts (headings, dividers, quotes)
    - Collapses multiple newlines to maximum of 2
    - Collapses multiple spaces to single space
    - Removes trailing/leading whitespace from lines
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text with consistent whitespace
    """
    if not text:
        return ""

    # Strip leading/trailing whitespace first
    text = text.strip()

    # Remove carriage returns and other control characters
    text = text.replace("\r", "")
    text = text.replace("\x00", "")
    
    # Remove common markdown artifacts that create empty sections
    text = re.sub(r"^\s*[#]+\s*$", "", text, flags=re.MULTILINE)  # Empty headings
    text = re.sub(r"^\s*[-*_]+\s*$", "", text, flags=re.MULTILINE)  # Empty dividers
    text = re.sub(r"^\s*>\s*$", "", text, flags=re.MULTILINE)  # Empty quotes
    
    # Aggressively collapse any sequence of 2+ newlines to exactly 2
    # This handles cases with hundreds of consecutive newlines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    
    # Clean up each line: collapse multiple spaces to single space
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # Strip leading/trailing whitespace from each line
        line = line.strip()
        # Collapse multiple spaces to single space
        line = re.sub(r"\s+", " ", line)
        # Only keep non-empty lines or intentional blank lines (for paragraph breaks)
        if line or (cleaned_lines and cleaned_lines[-1]):
            cleaned_lines.append(line)
    
    text = "\n".join(cleaned_lines)
    
    # Final aggressive pass: no more than 2 consecutive newlines anywhere
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    
    # Remove leading/trailing whitespace again
    text = text.strip()
    
    # Remove any remaining excessive whitespace patterns
    text = re.sub(r"[ \t]+\n", "\n", text)  # Trailing spaces before newlines
    text = re.sub(r"\n[ \t]+", "\n", text)  # Leading spaces after newlines
    
    return text

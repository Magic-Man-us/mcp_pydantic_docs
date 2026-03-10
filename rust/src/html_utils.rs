use regex::Regex;
use scraper::{Html, Selector};
use std::sync::LazyLock;

// Selectors for main content extraction
const MAIN_SELECTORS: &[&str] = &[
    "main[role='main']",
    "main",
    "div.md-content__inner",
    "div.md-content",
    "div.md-main__inner",
    "article",
    "div.md-typeset",
];

const REMOVE_SELECTORS: &[&str] = &[
    "nav", "header", "footer", "aside",
    ".md-header", ".md-sidebar", ".md-nav", ".md-footer",
    ".md-search", ".md-search__overlay", ".md-tabs",
    ".skip-link", ".sr-only", ".visually-hidden",
    "script", "style",
];

// Compiled regex patterns
static FENCE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?s)`{3,}.*?`{3,}").unwrap());
static PIPE_ROWS_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?m)^\s*\|.*\|\s*$").unwrap());
static LINE_NO_BURST_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?:^|\s)(?:\d{1,4}\s+){5,}\d{1,4}(?:\s|$)").unwrap());
static MULTI_WS_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s+").unwrap());
static EMPTY_HEADING_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?m)^\s*[#]+\s*$").unwrap());
static EMPTY_DIVIDER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?m)^\s*[-*_]+\s*$").unwrap());
static EMPTY_QUOTE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?m)^\s*>\s*$").unwrap());
static MULTI_NEWLINE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\n\s*\n\s*\n+").unwrap());
static TRAILING_SPACE_NL_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[ \t]+\n").unwrap());
static LEADING_SPACE_NL_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\n[ \t]+").unwrap());

/// Extract plain text from HTML, removing boilerplate (nav, header, footer, etc.)
/// and focusing on main content.
pub fn html_to_text(html: &str) -> String {
    let document = Html::parse_document(html);

    // Try to find main content
    let mut main_html = None;
    for sel_str in MAIN_SELECTORS {
        if let Ok(sel) = Selector::parse(sel_str) {
            if let Some(el) = document.select(&sel).next() {
                main_html = Some(el.html());
                break;
            }
        }
    }

    let working_html = main_html.as_deref().unwrap_or(html);
    let doc = Html::parse_document(working_html);

    // Collect element IDs to remove
    let mut remove_ids = Vec::new();
    for sel_str in REMOVE_SELECTORS {
        if let Ok(sel) = Selector::parse(sel_str) {
            for el in doc.select(&sel) {
                remove_ids.push(el.id());
            }
        }
    }

    // Extract text, skipping removed elements
    let mut text = String::new();
    for node in doc.root_element().descendants() {
        // Skip nodes under removed elements
        let mut skip = false;
        for ancestor in node.ancestors() {
            if remove_ids.contains(&ancestor.id()) {
                skip = true;
                break;
            }
        }
        if skip {
            continue;
        }

        if let Some(text_node) = node.value().as_text() {
            let t = text_node.trim();
            if !t.is_empty() {
                if !text.is_empty() {
                    text.push('\n');
                }
                text.push_str(t);
            }
        }
    }

    text
}

/// Extract headings with IDs from HTML: returns Vec<(anchor, title)>.
pub fn extract_headings(html: &str) -> Vec<(String, String)> {
    let document = Html::parse_document(html);
    let sel = match Selector::parse("h1[id],h2[id],h3[id]") {
        Ok(s) => s,
        Err(_) => return Vec::new(),
    };

    let mut out = Vec::new();
    for el in document.select(&sel) {
        if let Some(id) = el.value().attr("id") {
            let title: String = el.text().collect::<Vec<_>>().join(" ").trim().to_string();
            out.push((id.to_string(), title));
        }
    }
    out
}

/// Extract a section from HTML by anchor ID.
/// Collects content from the heading until the next heading of equal or higher level.
pub fn extract_section(html: &str, anchor: &str, max_len: usize) -> String {
    let document = Html::parse_document(html);

    // Find the target element by ID
    let id_sel = match Selector::parse(&format!("[id=\"{}\"]", anchor)) {
        Ok(s) => s,
        Err(_) => return String::new(),
    };

    let target = match document.select(&id_sel).next() {
        Some(el) => el,
        None => return String::new(),
    };

    // Determine heading level
    let tag_name = target.value().name();
    let level: u32 = if tag_name.starts_with('h') {
        tag_name[1..].parse().unwrap_or(2)
    } else {
        2
    };

    // Collect heading text
    let heading_text: String = target.text().collect::<Vec<_>>().join(" ").trim().to_string();
    let mut parts = vec![heading_text];

    // Walk siblings after the target
    let mut found_target = false;

    // We need to iterate through the document tree to find siblings after our target.
    // Use a simple approach: iterate all elements and collect text after our anchor
    // until we hit a heading of <= level.
    for el in document.root_element().descendants() {
        if el.id() == target.id() {
            found_target = true;
            continue;
        }
        if !found_target {
            continue;
        }

        if let Some(element) = el.value().as_element() {
            let name = element.name();
            if name.starts_with('h') && name.len() == 2 {
                if let Ok(h_level) = name[1..].parse::<u32>() {
                    if h_level <= level {
                        break;
                    }
                }
            }
        }

        if let Some(text_node) = el.value().as_text() {
            let t = text_node.trim();
            if !t.is_empty() {
                parts.push(t.to_string());
            }
        }
    }

    let text = parts.join("\n");
    if text.len() > max_len {
        text[..max_len].to_string()
    } else {
        text
    }
}

/// Clean a snippet for display: strip code fences, table rows, line numbers, etc.
pub fn clean_snippet(s: &str, max_len: usize) -> String {
    let mut result = FENCE_RE.replace_all(s, " ").to_string();
    result = PIPE_ROWS_RE.replace_all(&result, " ").to_string();
    result = LINE_NO_BURST_RE.replace_all(&result, " ").to_string();
    result = result.replace('|', " ").replace('`', " ");
    result = MULTI_WS_RE.replace_all(&result, " ").to_string();
    result = result.trim().to_string();
    if result.len() > max_len {
        result.truncate(max_len);
    }
    result
}

/// Normalize text: collapse whitespace, remove artifacts, etc.
pub fn normalize_text(text: &str) -> String {
    if text.is_empty() {
        return String::new();
    }

    let mut result = text.trim().to_string();

    // Remove carriage returns and null bytes
    result = result.replace('\r', "").replace('\0', "");

    // Remove empty markdown artifacts
    result = EMPTY_HEADING_RE.replace_all(&result, "").to_string();
    result = EMPTY_DIVIDER_RE.replace_all(&result, "").to_string();
    result = EMPTY_QUOTE_RE.replace_all(&result, "").to_string();

    // Collapse multiple newlines to max 2
    result = MULTI_NEWLINE_RE.replace_all(&result, "\n\n").to_string();

    // Clean each line
    let mut cleaned_lines: Vec<String> = Vec::new();
    for line in result.split('\n') {
        let trimmed = line.trim();
        let collapsed = MULTI_WS_RE.replace_all(trimmed, " ").to_string();
        if !collapsed.is_empty() || cleaned_lines.last().is_some_and(|l: &String| !l.is_empty()) {
            cleaned_lines.push(collapsed);
        }
    }

    result = cleaned_lines.join("\n");

    // Final pass: no more than 2 consecutive newlines
    while result.contains("\n\n\n") {
        result = result.replace("\n\n\n", "\n\n");
    }

    result = result.trim().to_string();
    result = TRAILING_SPACE_NL_RE.replace_all(&result, "\n").to_string();
    result = LEADING_SPACE_NL_RE.replace_all(&result, "\n").to_string();

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_html_to_text_basic() {
        let html = "<main><p>Hello world</p></main>";
        let text = html_to_text(html);
        assert!(text.contains("Hello world"));
    }

    #[test]
    fn test_html_to_text_removes_nav() {
        let html = "<nav>Nav</nav><main>Main content</main>";
        let text = html_to_text(html);
        assert!(!text.contains("Nav"));
        assert!(text.contains("Main content"));
    }

    #[test]
    fn test_extract_headings() {
        let html = r#"<h1 id="intro">Introduction</h1><h2 id="setup">Setup</h2>"#;
        let headings = extract_headings(html);
        assert_eq!(headings.len(), 2);
        assert_eq!(headings[0].0, "intro");
        assert_eq!(headings[0].1, "Introduction");
    }

    #[test]
    fn test_extract_section() {
        let html = r#"
            <h2 id="section-one">Section One</h2>
            <p>Content for section one.</p>
            <h2 id="section-two">Section Two</h2>
            <p>Content for section two.</p>
        "#;
        let section = extract_section(html, "section-one", 4000);
        assert!(section.contains("Section One"));
        assert!(section.contains("Content for section one"));
        assert!(!section.contains("Section Two"));
    }

    #[test]
    fn test_extract_section_missing_anchor() {
        let html = "<h2 id='exists'>Exists</h2><p>Content</p>";
        let section = extract_section(html, "nonexistent", 4000);
        assert!(section.is_empty());
    }

    #[test]
    fn test_clean_snippet() {
        let raw = "Text ```python\ncode\n``` more text | table |";
        let cleaned = clean_snippet(raw, 420);
        assert!(!cleaned.contains("```"));
        assert!(!cleaned.contains('|'));
    }

    #[test]
    fn test_normalize_text_empty() {
        assert_eq!(normalize_text(""), "");
    }

    #[test]
    fn test_normalize_text_collapses_newlines() {
        let text = "line1\n\n\n\n\nline2";
        let result = normalize_text(text);
        assert!(!result.contains("\n\n\n"));
    }

    #[test]
    fn test_normalize_text_collapses_spaces() {
        let text = "word1    word2     word3";
        let result = normalize_text(text);
        assert!(!result.contains("  "));
    }

    #[test]
    fn test_normalize_text_removes_cr() {
        let text = "line1\r\nline2";
        let result = normalize_text(text);
        assert!(!result.contains('\r'));
    }
}

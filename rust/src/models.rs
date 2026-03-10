use serde::{Deserialize, Serialize};

/// A single record from the JSONL index files.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocRecord {
    pub title: String,
    #[serde(default)]
    pub anchor: Option<String>,
    #[serde(default)]
    pub heading_level: i32,
    #[serde(default)]
    pub md_text: String,
    #[serde(default)]
    pub url: String,
    #[serde(default)]
    pub page: String,
    #[serde(default)]
    pub source_site: String,
}

/// A search hit returned to the MCP client.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchHit {
    pub title: String,
    pub url: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub anchor: Option<String>,
    pub snippet: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub heading_title: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResponse {
    pub results: Vec<SearchHit>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetResponse {
    pub url: String,
    pub path: String,
    pub text: String,
    pub html: String,
    pub truncated: bool,
    pub text_length: usize,
    pub html_length: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_chars: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SectionResponse {
    pub url: String,
    pub path: String,
    pub anchor: String,
    pub section: String,
    pub truncated: bool,
}

/// API alias mapping: symbol name → relative doc path.
pub fn api_aliases() -> Vec<(&'static str, &'static str)> {
    vec![
        ("BaseModel", "api/base_model/"),
        ("TypeAdapter", "api/type_adapter/"),
        ("ValidationError", "api/errors/"),
        ("Settings", "concepts/pydantic_settings/"),
    ]
}

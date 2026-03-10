use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde_json::Value;

use crate::bm25::{tokenize, Bm25Index};
use crate::html_utils;
use crate::models::*;

// Constants
const MAX_SNIPPET: usize = 800;
const MAX_SECTION: usize = 4000;
const SNIP_MAX: usize = 420;
const LOCAL_BASE_P: &str = "local://pydantic/";
const LOCAL_BASE_AI: &str = "local://pydantic-ai/";
const BASE_PYDANTIC: &str = "https://docs.pydantic.dev/latest/";
const BASE_PYDANTIC_AI: &str = "https://ai.pydantic.dev/";

/// The loaded documentation state: records + BM25 index.
pub struct DocState {
    records: Vec<DocRecord>,
    bm25: Bm25Index,
    doc_root: PathBuf,
    doc_root_ai: PathBuf,
    data_dir: PathBuf,
}

impl DocState {
    /// Load from JSONL files and build BM25 index in memory.
    pub fn load(data_dir: &Path, doc_root: &Path, doc_root_ai: &Path) -> Result<Self> {
        let pydantic_jsonl = data_dir.join("pydantic.jsonl");
        let pydantic_ai_jsonl = data_dir.join("pydantic_ai.jsonl");

        let mut records = Vec::new();

        for jsonl_path in &[&pydantic_jsonl, &pydantic_ai_jsonl] {
            if jsonl_path.exists() {
                let content = std::fs::read_to_string(jsonl_path)
                    .with_context(|| format!("Failed to read {}", jsonl_path.display()))?;
                for line in content.lines() {
                    let line = line.trim();
                    if line.is_empty() {
                        continue;
                    }
                    match serde_json::from_str::<DocRecord>(line) {
                        Ok(record) => records.push(record),
                        Err(e) => {
                            tracing::warn!("Skipping malformed JSONL line: {}", e);
                        }
                    }
                }
            } else {
                tracing::warn!("JSONL file not found: {}", jsonl_path.display());
            }
        }

        // Also load pydantic_settings if present
        let settings_jsonl = data_dir.join("pydantic_settings.jsonl");
        if settings_jsonl.exists() {
            let content = std::fs::read_to_string(&settings_jsonl)?;
            for line in content.lines() {
                let line = line.trim();
                if !line.is_empty() {
                    if let Ok(record) = serde_json::from_str::<DocRecord>(line) {
                        records.push(record);
                    }
                }
            }
        }

        tracing::info!("Loaded {} records from JSONL files", records.len());

        // Build BM25 index
        let corpus: Vec<Vec<String>> = records.iter().map(|r| tokenize(&r.md_text)).collect();
        let bm25 = Bm25Index::new(&corpus);
        tracing::info!("BM25 index built");

        Ok(DocState {
            records,
            bm25,
            doc_root: doc_root.to_path_buf(),
            doc_root_ai: doc_root_ai.to_path_buf(),
            data_dir: data_dir.to_path_buf(),
        })
    }

    fn display_url(&self, root: &Path, rel: &str) -> String {
        let base = if root == self.doc_root {
            LOCAL_BASE_P
        } else {
            LOCAL_BASE_AI
        };
        format!("{}{}", base, rel)
    }

    fn resolve_path_or_url(&self, path_or_url: &str) -> (PathBuf, String) {
        let s = path_or_url.trim();
        let (root, rel) = if s.starts_with(BASE_PYDANTIC) {
            (&self.doc_root, &s[BASE_PYDANTIC.len()..])
        } else if s.starts_with(BASE_PYDANTIC_AI) {
            (&self.doc_root_ai, &s[BASE_PYDANTIC_AI.len()..])
        } else if s.starts_with(LOCAL_BASE_P) {
            (&self.doc_root, &s[LOCAL_BASE_P.len()..])
        } else if s.starts_with(LOCAL_BASE_AI) {
            (&self.doc_root_ai, &s[LOCAL_BASE_AI.len()..])
        } else {
            (&self.doc_root, s)
        };

        let rel = rel.split('#').next().unwrap_or("");
        let rel = rel.trim_start_matches('/').replace("..", "");
        (root.clone(), rel)
    }

    fn read_page(&self, root: &Path, rel: &str) -> Result<String> {
        let rel = rel.trim_start_matches('/').replace("..", "");
        let path = root.join(&rel);
        let resolved = path
            .canonicalize()
            .with_context(|| format!("File not found: {}", rel))?;

        // Security: ensure path is within root
        let root_resolved = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
        if !resolved.starts_with(&root_resolved) {
            anyhow::bail!("Path traversal blocked: {}", rel);
        }

        std::fs::read_to_string(&resolved)
            .with_context(|| format!("Failed to read: {}", resolved.display()))
    }

    // ---- MCP Tool Implementations ----

    pub fn health_ping(&self) -> Value {
        serde_json::json!("pong")
    }

    pub fn health_validate(&self) -> Value {
        serde_json::json!({
            "valid": !self.records.is_empty(),
            "message": if self.records.is_empty() { "No records loaded" } else { "Search index loaded successfully" },
            "records_count": self.records.len(),
        })
    }

    pub fn pydantic_mode(&self) -> Value {
        let count_html = |root: &Path| -> usize {
            if !root.exists() {
                return 0;
            }
            walkdir(root, "html")
        };

        serde_json::json!({
            "offline_only": true,
            "doc_root": self.doc_root.display().to_string(),
            "doc_root_ai": self.doc_root_ai.display().to_string(),
            "data_dir": self.data_dir.display().to_string(),
            "bm25_present": !self.records.is_empty(),
            "counts": {
                "pydantic_html": count_html(&self.doc_root),
                "pydantic_ai_html": count_html(&self.doc_root_ai),
            },
            "display_bases": {
                "pydantic": LOCAL_BASE_P,
                "pydantic_ai": LOCAL_BASE_AI,
            },
        })
    }

    pub fn pydantic_search(
        &self,
        query: &str,
        k: usize,
        site: Option<&str>,
        heading: Option<&str>,
        keywords: Option<&str>,
    ) -> Value {
        let k = k.clamp(1, 50);
        let tokens = tokenize(query);
        let scored = self.bm25.query(&tokens, k * 3);
        let q_str = tokens.join(" ");

        let mut hits: Vec<SearchHit> = scored
            .iter()
            .map(|&(idx, _score)| {
                let r = &self.records[idx];
                let text = &r.md_text;

                // Find snippet around query terms
                let pos = text.to_lowercase().find(&q_str);
                let raw = match pos {
                    Some(p) => {
                        let start = p.saturating_sub(120);
                        let end = (p + 200).min(text.len());
                        &text[start..end]
                    }
                    None => &text[..text.len().min(MAX_SNIPPET)],
                };
                let snippet = html_utils::clean_snippet(raw, SNIP_MAX);

                let root = if r.source_site == "pydantic_ai" {
                    &self.doc_root_ai
                } else {
                    &self.doc_root
                };

                SearchHit {
                    title: r.title.clone(),
                    url: self.display_url(root, &r.page),
                    anchor: r.anchor.clone(),
                    snippet,
                    heading_title: None,
                }
            })
            .collect();

        // Site filter
        if let Some(site_filter) = site {
            let prefix = if site_filter == "pydantic_ai" {
                LOCAL_BASE_AI
            } else {
                LOCAL_BASE_P
            };
            hits.retain(|h| h.url.starts_with(prefix));
        }

        // Heading filter
        if let Some(hq) = heading {
            let hq_lower = hq.to_lowercase();
            hits.retain(|h| {
                h.snippet.to_lowercase().contains(&hq_lower)
                    || h.title.to_lowercase().contains(&hq_lower)
            });
        }

        // Keywords filter
        if let Some(kw) = keywords {
            let kw_tokens: Vec<String> = kw
                .split_whitespace()
                .filter(|t| !t.is_empty())
                .map(|t| t.to_lowercase())
                .collect();
            hits.retain(|h| {
                let hay = format!("{} {}", h.title, h.snippet).to_lowercase();
                kw_tokens.iter().all(|t| hay.contains(t.as_str()))
            });
        }

        hits.truncate(k);

        let response = SearchResponse { results: hits };
        serde_json::to_value(&response).unwrap_or_default()
    }

    pub fn pydantic_get(&self, path_or_url: &str, max_chars: Option<usize>) -> Value {
        let (root, rel) = self.resolve_path_or_url(path_or_url);
        let html_str = match self.read_page(&root, &rel) {
            Ok(h) => h,
            Err(e) => {
                return serde_json::json!({"error": e.to_string()});
            }
        };

        let text = html_utils::html_to_text(&html_str);
        let text = html_utils::normalize_text(&text);
        let url = self.display_url(&root, &rel);

        let text_length = text.len();
        let html_length = html_str.len();
        let mut truncated = false;

        let (final_text, final_html) = if let Some(mc) = max_chars {
            if mc > 0 {
                let t = if text_length > mc {
                    truncated = true;
                    format!("{}\n\n[... truncated ...]", &text[..mc])
                } else {
                    text
                };
                let h = if html_length > mc {
                    truncated = true;
                    format!("{}\n<!-- ... truncated ... -->", &html_str[..mc])
                } else {
                    html_str
                };
                (t, h)
            } else {
                (text, html_str)
            }
        } else {
            (text, html_str)
        };

        let response = GetResponse {
            url,
            path: rel,
            text: final_text,
            html: final_html,
            truncated,
            text_length,
            html_length,
            max_chars,
        };
        serde_json::to_value(&response).unwrap_or_default()
    }

    pub fn pydantic_section(&self, path_or_url: &str, anchor: &str) -> Value {
        let (root, rel) = self.resolve_path_or_url(path_or_url);
        let html_str = match self.read_page(&root, &rel) {
            Ok(h) => h,
            Err(e) => {
                return serde_json::json!({"error": e.to_string()});
            }
        };

        let section = html_utils::extract_section(&html_str, anchor, MAX_SECTION);
        let url = format!("{}#{}",self.display_url(&root, &rel), anchor);

        let response = SectionResponse {
            url,
            path: rel,
            anchor: anchor.to_string(),
            section: section.clone(),
            truncated: section.len() >= MAX_SECTION,
        };
        serde_json::to_value(&response).unwrap_or_default()
    }

    pub fn pydantic_api(&self, symbol: &str, anchor: Option<&str>) -> Value {
        let aliases = api_aliases();
        let rel = aliases
            .iter()
            .find(|(name, _)| *name == symbol)
            .map(|(_, path)| *path)
            .unwrap_or("api/");

        let rel_file = if rel.ends_with(".html") {
            rel.to_string()
        } else {
            format!("{}index.html", rel)
        };

        let html_str = match self.read_page(&self.doc_root, &rel_file) {
            Ok(h) => h,
            Err(e) => {
                return serde_json::json!({"error": e.to_string()});
            }
        };

        if let Some(anch) = anchor {
            let section = html_utils::extract_section(&html_str, anch, MAX_SECTION);
            let url = format!("{}#{}", self.display_url(&self.doc_root, rel), anch);
            serde_json::json!({
                "symbol": symbol,
                "url": url,
                "section": section,
            })
        } else {
            let text = html_utils::html_to_text(&html_str);
            let url = self.display_url(&self.doc_root, rel);
            serde_json::json!({
                "symbol": symbol,
                "url": url,
                "text": text,
            })
        }
    }

    pub fn admin_cache_status(&self) -> Value {
        let count_jsonl_records = |path: &Path| -> usize {
            if !path.exists() {
                return 0;
            }
            std::fs::read_to_string(path)
                .map(|c| c.lines().filter(|l| !l.trim().is_empty()).count())
                .unwrap_or(0)
        };

        serde_json::json!({
            "paths": {
                "doc_root": self.doc_root.display().to_string(),
                "doc_root_ai": self.doc_root_ai.display().to_string(),
                "data_dir": self.data_dir.display().to_string(),
            },
            "documentation": {
                "pydantic": {
                    "exists": self.doc_root.exists(),
                    "html_files": if self.doc_root.exists() { walkdir(&self.doc_root, "html") } else { 0 },
                },
                "pydantic_ai": {
                    "exists": self.doc_root_ai.exists(),
                    "html_files": if self.doc_root_ai.exists() { walkdir(&self.doc_root_ai, "html") } else { 0 },
                },
            },
            "jsonl_data": {
                "pydantic": {
                    "exists": self.data_dir.join("pydantic.jsonl").exists(),
                    "records": count_jsonl_records(&self.data_dir.join("pydantic.jsonl")),
                },
                "pydantic_ai": {
                    "exists": self.data_dir.join("pydantic_ai.jsonl").exists(),
                    "records": count_jsonl_records(&self.data_dir.join("pydantic_ai.jsonl")),
                },
            },
            "search_indices": {
                "records_loaded": self.records.len(),
                "valid": !self.records.is_empty(),
            },
            "offline_mode": true,
        })
    }
}

/// Count files with given extension under a directory.
fn walkdir(root: &Path, ext: &str) -> usize {
    let mut count = 0;
    if let Ok(entries) = std::fs::read_dir(root) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                count += walkdir(&path, ext);
            } else if path.extension().and_then(|e| e.to_str()) == Some(ext) {
                count += 1;
            }
        }
    }
    count
}

// ---- MCP JSON-RPC over stdio ----

/// A JSON-RPC request.
#[derive(Debug, Deserialize)]
struct JsonRpcRequest {
    jsonrpc: String,
    #[serde(default)]
    id: Option<Value>,
    method: String,
    #[serde(default)]
    params: Option<Value>,
}

/// A JSON-RPC response.
#[derive(Debug, Serialize)]
struct JsonRpcResponse {
    jsonrpc: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    id: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<Value>,
}

use serde::{Deserialize, Serialize};

/// Handle the MCP initialize request.
fn handle_initialize(id: Option<Value>) -> JsonRpcResponse {
    JsonRpcResponse {
        jsonrpc: "2.0".into(),
        id,
        result: Some(serde_json::json!({
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "pydantic-docs",
                "version": "0.1.0"
            }
        })),
        error: None,
    }
}

/// Handle tools/list request.
fn handle_tools_list(id: Option<Value>) -> JsonRpcResponse {
    let tools = serde_json::json!({
        "tools": [
            {
                "name": "health_ping",
                "description": "Returns simple pong",
                "inputSchema": { "type": "object", "properties": {} }
            },
            {
                "name": "health_validate",
                "description": "Validate search indices and data integrity",
                "inputSchema": { "type": "object", "properties": {} }
            },
            {
                "name": "pydantic_mode",
                "description": "Report data roots and offline mode.",
                "inputSchema": { "type": "object", "properties": {} }
            },
            {
                "name": "pydantic_search",
                "description": "Search local Pydantic + Pydantic-AI docs with filters.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": { "type": "string", "description": "Search query" },
                        "k": { "type": "integer", "description": "Number of results", "default": 10 },
                        "site": { "type": "string", "description": "Filter by site: pydantic or pydantic_ai", "enum": ["pydantic", "pydantic_ai"] },
                        "heading": { "type": "string", "description": "Filter by heading title substring" },
                        "keywords": { "type": "string", "description": "Space-separated required tokens" }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "pydantic_get",
                "description": "Fetch a local doc page and return plain text + html. Supports chunking via max_chars.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path_or_url": { "type": "string", "description": "Path or URL to doc page" },
                        "max_chars": { "type": "integer", "description": "Optional max chars for truncation" }
                    },
                    "required": ["path_or_url"]
                }
            },
            {
                "name": "pydantic_section",
                "description": "Extract a section by anchor from a local page.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path_or_url": { "type": "string", "description": "Path or URL to doc page" },
                        "anchor": { "type": "string", "description": "Section anchor/ID" }
                    },
                    "required": ["path_or_url", "anchor"]
                }
            },
            {
                "name": "pydantic_api",
                "description": "Jump to an API page by symbol name. Optional anchor.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": { "type": "string", "description": "API symbol name" },
                        "anchor": { "type": "string", "description": "Optional anchor within API page" }
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "admin_cache_status",
                "description": "Get detailed status of documentation cache.",
                "inputSchema": { "type": "object", "properties": {} }
            }
        ]
    });

    JsonRpcResponse {
        jsonrpc: "2.0".into(),
        id,
        result: Some(tools),
        error: None,
    }
}

/// Handle tools/call request.
fn handle_tool_call(state: &DocState, id: Option<Value>, params: &Value) -> JsonRpcResponse {
    let tool_name = params
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let arguments = params.get("arguments").cloned().unwrap_or(serde_json::json!({}));

    let result = match tool_name {
        "health_ping" => state.health_ping(),
        "health_validate" => state.health_validate(),
        "pydantic_mode" => state.pydantic_mode(),
        "pydantic_search" => {
            let query = arguments.get("query").and_then(|v| v.as_str()).unwrap_or("");
            let k = arguments.get("k").and_then(|v| v.as_u64()).unwrap_or(10) as usize;
            let site = arguments.get("site").and_then(|v| v.as_str());
            let heading = arguments.get("heading").and_then(|v| v.as_str());
            let keywords = arguments.get("keywords").and_then(|v| v.as_str());
            state.pydantic_search(query, k, site, heading, keywords)
        }
        "pydantic_get" => {
            let path_or_url = arguments
                .get("path_or_url")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let max_chars = arguments
                .get("max_chars")
                .and_then(|v| v.as_u64())
                .map(|v| v as usize);
            state.pydantic_get(path_or_url, max_chars)
        }
        "pydantic_section" => {
            let path_or_url = arguments
                .get("path_or_url")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let anchor = arguments
                .get("anchor")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            state.pydantic_section(path_or_url, anchor)
        }
        "pydantic_api" => {
            let symbol = arguments
                .get("symbol")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let anchor = arguments.get("anchor").and_then(|v| v.as_str());
            state.pydantic_api(symbol, anchor)
        }
        "admin_cache_status" => state.admin_cache_status(),
        _ => {
            return JsonRpcResponse {
                jsonrpc: "2.0".into(),
                id,
                result: None,
                error: Some(serde_json::json!({
                    "code": -32601,
                    "message": format!("Unknown tool: {}", tool_name)
                })),
            };
        }
    };

    // Wrap in MCP content format
    let content = serde_json::json!({
        "content": [{
            "type": "text",
            "text": serde_json::to_string(&result).unwrap_or_default()
        }]
    });

    JsonRpcResponse {
        jsonrpc: "2.0".into(),
        id,
        result: Some(content),
        error: None,
    }
}

/// Run the MCP server, reading JSON-RPC from stdin and writing to stdout.
pub async fn run_server(state: DocState) -> Result<()> {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

    let stdin = tokio::io::stdin();
    let mut stdout = tokio::io::stdout();
    let mut reader = BufReader::new(stdin);
    let mut line_buf = String::new();

    tracing::info!("MCP server ready, listening on stdio");

    loop {
        line_buf.clear();
        let n = reader.read_line(&mut line_buf).await?;
        if n == 0 {
            // EOF
            break;
        }

        let line = line_buf.trim();
        if line.is_empty() {
            continue;
        }

        let request: JsonRpcRequest = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(e) => {
                let err_response = JsonRpcResponse {
                    jsonrpc: "2.0".into(),
                    id: None,
                    result: None,
                    error: Some(serde_json::json!({
                        "code": -32700,
                        "message": format!("Parse error: {}", e)
                    })),
                };
                let out = serde_json::to_string(&err_response)? + "\n";
                stdout.write_all(out.as_bytes()).await?;
                stdout.flush().await?;
                continue;
            }
        };

        let response = match request.method.as_str() {
            "initialize" => handle_initialize(request.id),
            "initialized" => continue, // notification, no response
            "notifications/initialized" => continue,
            "tools/list" => handle_tools_list(request.id),
            "tools/call" => {
                let params = request.params.unwrap_or(serde_json::json!({}));
                handle_tool_call(&state, request.id, &params)
            }
            "ping" => JsonRpcResponse {
                jsonrpc: "2.0".into(),
                id: request.id,
                result: Some(serde_json::json!({})),
                error: None,
            },
            _ => {
                // For notifications (no id), just skip
                if request.id.is_none() {
                    continue;
                }
                JsonRpcResponse {
                    jsonrpc: "2.0".into(),
                    id: request.id,
                    result: None,
                    error: Some(serde_json::json!({
                        "code": -32601,
                        "message": format!("Method not found: {}", request.method)
                    })),
                }
            }
        };

        let out = serde_json::to_string(&response)? + "\n";
        stdout.write_all(out.as_bytes()).await?;
        stdout.flush().await?;
    }

    Ok(())
}

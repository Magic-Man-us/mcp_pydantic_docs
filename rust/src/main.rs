#![allow(dead_code)]

mod bm25;
mod html_utils;
mod models;
mod server;

use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

#[derive(Parser)]
#[command(name = "mcp-pydantic-docs", about = "MCP server for Pydantic documentation")]
struct Cli {
    /// Path to the data directory containing JSONL files
    #[arg(long, env = "PDA_DATA_DIR")]
    data_dir: Option<PathBuf>,

    /// Path to the Pydantic docs root
    #[arg(long, env = "PDA_DOC_ROOT")]
    doc_root: Option<PathBuf>,

    /// Path to the Pydantic AI docs root
    #[arg(long, env = "PDA_DOC_ROOT_AI")]
    doc_root_ai: Option<PathBuf>,
}

fn find_project_root() -> PathBuf {
    // Start from the executable location and walk up
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."));

    // Check if we're in the rust/target/ directory structure
    for ancestor in exe_dir.ancestors() {
        if ancestor.join("data").exists() {
            return ancestor.to_path_buf();
        }
    }

    // Fallback: try current working directory
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for ancestor in cwd.ancestors() {
        if ancestor.join("data").exists() {
            return ancestor.to_path_buf();
        }
    }

    cwd
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing to stderr (stdout is for JSON-RPC)
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let cli = Cli::parse();
    let project_root = find_project_root();

    let data_dir = cli
        .data_dir
        .unwrap_or_else(|| project_root.join("data"));
    let doc_root = cli
        .doc_root
        .unwrap_or_else(|| project_root.join("docs_raw").join("pydantic"));
    let doc_root_ai = cli
        .doc_root_ai
        .unwrap_or_else(|| project_root.join("docs_raw").join("pydantic_ai"));

    tracing::info!("Project root: {}", project_root.display());
    tracing::info!("Data dir: {}", data_dir.display());

    let state = server::DocState::load(&data_dir, &doc_root, &doc_root_ai)?;

    server::run_server(state).await
}

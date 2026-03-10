//! CLI tool for building the BM25 search index from JSONL files.
//!
//! This replaces `python -m mcp_pydantic_docs.indexer` for the index-building step.
//! It reads the JSONL files and validates them, then reports statistics.
//! The actual BM25 index is built in-memory at server startup (no pickle needed).

#![allow(dead_code)]

mod bm25;
mod html_utils;
mod models;
mod server;

use std::path::PathBuf;
use std::time::Instant;

use anyhow::Result;
use clap::Parser;

use crate::models::DocRecord;

#[derive(Parser)]
#[command(
    name = "mcp-indexer",
    about = "Validate and inspect JSONL documentation index files"
)]
struct Cli {
    /// Path to the data directory containing JSONL files
    #[arg(long, env = "PDA_DATA_DIR")]
    data_dir: Option<PathBuf>,

    /// Validate JSONL files and report statistics
    #[arg(long, default_value = "true")]
    validate: bool,

    /// Build a test BM25 index and run a sample query
    #[arg(long)]
    test_query: Option<String>,
}

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let cli = Cli::parse();

    // Find project root
    let cwd = std::env::current_dir()?;
    let project_root = cwd
        .ancestors()
        .find(|p| p.join("data").exists())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| cwd.clone());

    let data_dir = cli.data_dir.unwrap_or_else(|| project_root.join("data"));

    println!("==========================================================");
    println!("PYDANTIC DOCS INDEX VALIDATOR (Rust)");
    println!("==========================================================");
    println!("Data directory: {}", data_dir.display());
    println!();

    let start = Instant::now();
    let mut total_records = 0;

    for name in &["pydantic.jsonl", "pydantic_ai.jsonl", "pydantic_settings.jsonl"] {
        let path = data_dir.join(name);
        if !path.exists() {
            if *name != "pydantic_settings.jsonl" {
                println!("  WARNING: {} not found", name);
            }
            continue;
        }

        let content = std::fs::read_to_string(&path)?;
        let mut count = 0;
        let mut errors = 0;

        for line in content.lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            match serde_json::from_str::<DocRecord>(line) {
                Ok(_) => count += 1,
                Err(e) => {
                    errors += 1;
                    if errors <= 3 {
                        eprintln!("  Parse error in {}: {}", name, e);
                    }
                }
            }
        }

        let size = path.metadata()?.len() as f64 / 1024.0 / 1024.0;
        println!("  {}: {} records ({:.1} MB, {} errors)", name, count, size, errors);
        total_records += count;
    }

    println!();
    println!("Total records: {}", total_records);

    // Optionally build index and run test query
    if let Some(query) = cli.test_query {
        println!();
        println!("Building BM25 index...");
        let build_start = Instant::now();

        let mut records = Vec::new();
        for name in &["pydantic.jsonl", "pydantic_ai.jsonl"] {
            let path = data_dir.join(name);
            if !path.exists() {
                continue;
            }
            let content = std::fs::read_to_string(&path)?;
            for line in content.lines() {
                let line = line.trim();
                if !line.is_empty() {
                    if let Ok(record) = serde_json::from_str::<DocRecord>(line) {
                        records.push(record);
                    }
                }
            }
        }

        let corpus: Vec<Vec<String>> = records.iter().map(|r| bm25::tokenize(&r.md_text)).collect();
        let index = bm25::Bm25Index::new(&corpus);
        println!("  Index built in {:.1}ms", build_start.elapsed().as_millis());

        let tokens = bm25::tokenize(&query);
        let results = index.query(&tokens, 5);

        println!();
        println!("Query: \"{}\"", query);
        println!("Results:");
        for (i, (doc_id, score)) in results.iter().enumerate() {
            let r = &records[*doc_id];
            let snippet = &r.md_text[..r.md_text.len().min(100)];
            println!(
                "  {}. [score={:.3}] {} - {}",
                i + 1,
                score,
                r.title,
                snippet.replace('\n', " ")
            );
        }
    }

    let elapsed = start.elapsed();
    println!();
    println!("==========================================================");
    println!("Completed in {:.1}ms", elapsed.as_millis());
    println!("==========================================================");

    Ok(())
}

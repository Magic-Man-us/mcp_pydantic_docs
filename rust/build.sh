#!/bin/bash
set -e

echo "=========================================="
echo "Building Rust MCP Server"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check for Rust toolchain
if ! command -v cargo &> /dev/null; then
    echo "  ERROR: cargo not found"
    echo ""
    echo "  Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi
echo "  cargo: $(cargo --version)"
echo ""

# Build release binary
echo "Building release binary..."
cargo build --release
echo ""

BINARY="$SCRIPT_DIR/target/release/mcp-pydantic-docs"
INDEXER="$SCRIPT_DIR/target/release/mcp-indexer"

echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "Binaries:"
echo "  Server:  $BINARY"
echo "  Indexer: $INDEXER"
echo ""

# Validate JSONL data
echo "Validating data files..."
"$INDEXER" --data-dir "$SCRIPT_DIR/../data" 2>/dev/null
echo ""

echo "MCP client configuration:"
echo ""
echo '  {'
echo '    "mcpServers": {'
echo '      "pydantic-docs": {'
echo '        "command": "'$BINARY'",'
echo '        "args": ["--data-dir", "'$SCRIPT_DIR/../data'"]'
echo '      }'
echo '    }'
echo '  }'
echo ""
echo "=========================================="

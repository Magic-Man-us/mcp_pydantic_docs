#!/bin/bash
set -e

echo "=========================================="
echo "Pydantic Documentation MCP Server"
echo "Installation Script"
echo "=========================================="
echo ""

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Installation directory: $SCRIPT_DIR"
echo ""

# Step 1: Check uv is installed
echo "Step 1: Checking for uv package manager..."
if ! command -v uv &> /dev/null; then
    echo "  ✗ uv not found"
    echo ""
    echo "Please install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    exit 1
fi
echo "  ✓ uv found: $(uv --version)"
echo ""

# Step 2: Install dependencies
echo "Step 2: Installing dependencies..."
uv sync
echo "  ✓ Dependencies installed"
echo ""

# Step 3: Check if JSONL files exist
echo "Step 3: Checking for documentation data..."
PYDANTIC_JSONL="data/pydantic.jsonl"
PYDANTIC_AI_JSONL="data/pydantic_ai.jsonl"

if [ -f "$PYDANTIC_JSONL" ] && [ -f "$PYDANTIC_AI_JSONL" ]; then
    echo "  ✓ JSONL files found"
    echo "    - pydantic.jsonl: $(du -h $PYDANTIC_JSONL | cut -f1)"
    echo "    - pydantic_ai.jsonl: $(du -h $PYDANTIC_AI_JSONL | cut -f1)"
else
    echo "  ✗ JSONL files not found"
    echo ""
    echo "Would you like to download documentation now? (y/N)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo ""
        echo "  Downloading documentation..."
        uv run python -m mcp_pydantic_docs.setup --download --build-index
        echo "  ✓ Documentation downloaded and indexed"
    else
        echo "  Skipping download. You'll need to run this later:"
        echo "    uv run python -m mcp_pydantic_docs.setup --download --build-index"
        exit 0
    fi
fi
echo ""

# Step 4: Build search indices
echo "Step 4: Building search indices..."
if [ -f "data/pydantic_all_bm25.pkl" ] && [ -f "data/pydantic_all_records.pkl" ]; then
    echo "  ✓ Search indices already exist"
else
    uv run python -m mcp_pydantic_docs.indexer
    echo "  ✓ Search indices built"
fi
echo ""

# Step 5: Verify installation
echo "Step 5: Verifying installation..."
uv run python -c "from mcp_pydantic_docs import mcp; print('  ✓ Package imports successfully')"
echo ""

# Step 6: Display configuration
echo "=========================================="
echo "✓ Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Add to your MCP settings (e.g., cline_mcp_settings.json):"
echo ""
echo '   {'
echo '     "mcpServers": {'
echo '       "pydantic-docs": {'
echo '         "disabled": false,'
echo '         "timeout": 60,'
echo '         "type": "stdio",'
echo '         "command": "uv",'
echo '         "args": ['
echo '           "--directory",'
echo "           \"$SCRIPT_DIR\","
echo '           "run",'
echo '           "mcp-pydantic-docs"'
echo '         ]'
echo '       }'
echo '     }'
echo '   }'
echo ""
echo "2. Restart your MCP client (e.g., reload VS Code)"
echo ""
echo "3. Test with: pydantic.search(query='BaseModel')"
echo ""
echo "Documentation: See README.md for full details"
echo "=========================================="

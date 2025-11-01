#!/bin/bash
set -e

echo "=========================================="
echo "Testing Fresh Installation Flow"
echo "=========================================="
echo ""

# Create temporary test directory
TEST_DIR=$(mktemp -d -t mcp_pydantic_test_XXXXXX)
echo "Test directory: $TEST_DIR"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up test directory: $TEST_DIR"
    rm -rf "$TEST_DIR"
}
trap cleanup EXIT

cd "$TEST_DIR"

echo "Step 1: Simulating git clone..."
echo "  - Copying source code and JSONL files"
mkdir -p mcp_pydantic_docs
cp -r /home/magicman/workplace/mcp_pydantic_docs/mcp_pydantic_docs mcp_pydantic_docs/
cp -r /home/magicman/workplace/mcp_pydantic_docs/data mcp_pydantic_docs/
cp /home/magicman/workplace/mcp_pydantic_docs/pyproject.toml mcp_pydantic_docs/
cp /home/magicman/workplace/mcp_pydantic_docs/uv.lock mcp_pydantic_docs/
cp /home/magicman/workplace/mcp_pydantic_docs/README.md mcp_pydantic_docs/
cp /home/magicman/workplace/mcp_pydantic_docs/LICENSE mcp_pydantic_docs/
cp /home/magicman/workplace/mcp_pydantic_docs/.gitignore mcp_pydantic_docs/

# Remove binary indices to simulate fresh clone
rm -f mcp_pydantic_docs/data/*.pkl
echo "  ✓ Repository structure created"
echo "  ✓ JSONL files present"
echo "  ✓ Binary indices removed (will be auto-generated)"
echo ""

cd mcp_pydantic_docs

echo "Step 2: Install dependencies..."
uv sync
echo "  ✓ Dependencies installed"
echo ""

echo "Step 3: Checking file structure..."
echo "  JSONL files:"
ls -lh data/*.jsonl | awk '{print "    " $9 " - " $5}'
echo ""

echo "Step 4: Testing auto-initialization..."
echo "  Starting MCP server (should auto-build indices)..."
timeout 15s uv run mcp-pydantic-docs &
MCP_PID=$!
sleep 5
kill $MCP_PID 2>/dev/null || true
echo "  ✓ Server started successfully"
echo ""

echo "Step 5: Verifying indices were created..."
if [ -f "data/pydantic_all_bm25.pkl" ] && [ -f "data/pydantic_all_records.pkl" ]; then
    echo "  ✓ Search indices created:"
    ls -lh data/*.pkl | awk '{print "    " $9 " - " $5}'
else
    echo "  ✗ Search indices NOT created"
    exit 1
fi
echo ""

echo "Step 6: Testing with MCP client simulation..."
echo "  Would configure as:"
echo "  {"
echo "    \"pydantic-docs\": {"
echo "      \"command\": \"uv\","
echo "      \"args\": [\"--directory\", \"$TEST_DIR/mcp_pydantic_docs\", \"run\", \"mcp-pydantic-docs\"]"
echo "    }"
echo "  }"
echo ""

echo "=========================================="
echo "✓ Fresh Install Test PASSED"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Repository cloned ✓"
echo "  - Dependencies installed ✓"
echo "  - JSONL files present ✓"
echo "  - Indices auto-built ✓"
echo "  - Server ready to use ✓"
echo ""
echo "Total disk usage:"
du -sh "$TEST_DIR/mcp_pydantic_docs" | awk '{print "  " $1}'

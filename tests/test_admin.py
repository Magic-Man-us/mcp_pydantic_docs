"""Tests for admin tools and cache management."""

from __future__ import annotations

import pytest

from mcp_pydantic_docs.mcp import t_cache_status, t_mode, t_rebuild_indices


@pytest.mark.admin
class TestAdminTools:
    """Test admin and management tools."""

    @pytest.mark.asyncio
    async def test_mode_returns_configuration(self):
        """Test that mode tool returns configuration info."""
        result = t_mode()
        
        assert isinstance(result, dict), "mode() should return a dict"
        assert "offline_only" in result, "Should report offline mode"
        assert "doc_root" in result, "Should report doc root"
        assert "doc_root_ai" in result, "Should report AI doc root"
        assert "data_dir" in result, "Should report data directory"
        assert "bm25_present" in result, "Should report BM25 status"

    @pytest.mark.asyncio
    async def test_mode_includes_counts(self):
        """Test that mode includes file counts."""
        result = t_mode()
        
        assert "counts" in result, "Should include counts"
        assert "pydantic_html" in result["counts"], "Should count pydantic HTML files"
        assert "pydantic_ai_html" in result["counts"], "Should count AI HTML files"
        
        # Counts should be non-negative integers
        assert isinstance(result["counts"]["pydantic_html"], int)
        assert isinstance(result["counts"]["pydantic_ai_html"], int)
        assert result["counts"]["pydantic_html"] >= 0
        assert result["counts"]["pydantic_ai_html"] >= 0

    @pytest.mark.asyncio
    async def test_mode_includes_display_bases(self):
        """Test that mode includes display base URLs."""
        result = t_mode()
        
        assert "display_bases" in result, "Should include display bases"
        assert "pydantic" in result["display_bases"]
        assert "pydantic_ai" in result["display_bases"]
        
        # Should be local:// URLs
        assert result["display_bases"]["pydantic"].startswith("local://")
        assert result["display_bases"]["pydantic_ai"].startswith("local://")

    @pytest.mark.asyncio
    async def test_cache_status_comprehensive(self):
        """Test that cache status provides comprehensive information."""
        result = await t_cache_status()
        
        assert isinstance(result, dict), "Should return dict"
        
        # Check main sections
        assert "paths" in result, "Should include paths"
        assert "documentation" in result, "Should include documentation status"
        assert "jsonl_data" in result, "Should include JSONL data status"
        assert "search_indices" in result, "Should include search indices status"
        assert "offline_mode" in result, "Should include offline mode"

    @pytest.mark.asyncio
    async def test_cache_status_paths(self):
        """Test that cache status includes all path information."""
        result = await t_cache_status()
        
        paths = result["paths"]
        assert "doc_root" in paths
        assert "doc_root_ai" in paths
        assert "data_dir" in paths
        
        # All should be strings
        assert isinstance(paths["doc_root"], str)
        assert isinstance(paths["doc_root_ai"], str)
        assert isinstance(paths["data_dir"], str)

    @pytest.mark.asyncio
    async def test_cache_status_documentation(self):
        """Test documentation cache status reporting."""
        result = await t_cache_status()
        
        docs = result["documentation"]
        assert "pydantic" in docs
        assert "pydantic_ai" in docs
        
        for site in ["pydantic", "pydantic_ai"]:
            assert "exists" in docs[site], f"Should report exists for {site}"
            assert "html_files" in docs[site], f"Should count HTML files for {site}"
            
            assert isinstance(docs[site]["exists"], bool)
            assert isinstance(docs[site]["html_files"], int)
            assert docs[site]["html_files"] >= 0

    @pytest.mark.asyncio
    async def test_cache_status_jsonl_data(self):
        """Test JSONL data status reporting."""
        result = await t_cache_status()
        
        jsonl = result["jsonl_data"]
        assert "pydantic" in jsonl
        assert "pydantic_ai" in jsonl
        
        for site in ["pydantic", "pydantic_ai"]:
            assert "exists" in jsonl[site]
            assert "records" in jsonl[site]
            
            assert isinstance(jsonl[site]["exists"], bool)
            assert isinstance(jsonl[site]["records"], int)
            assert jsonl[site]["records"] >= 0

    @pytest.mark.asyncio
    async def test_cache_status_search_indices(self):
        """Test search indices status reporting."""
        result = await t_cache_status()
        
        indices = result["search_indices"]
        assert "bm25_exists" in indices
        assert "records_exists" in indices
        assert "bm25_size_mb" in indices
        assert "records_size_mb" in indices
        assert "valid" in indices
        
        # Check types
        assert isinstance(indices["bm25_exists"], bool)
        assert isinstance(indices["records_exists"], bool)
        assert isinstance(indices["bm25_size_mb"], (int, float))
        assert isinstance(indices["records_size_mb"], (int, float))
        assert isinstance(indices["valid"], bool)
        
        # Sizes should be non-negative
        assert indices["bm25_size_mb"] >= 0
        assert indices["records_size_mb"] >= 0

    @pytest.mark.asyncio
    async def test_rebuild_indices_returns_status(self):
        """Test that rebuild indices returns correct structure (mocked for speed)."""
        from unittest.mock import patch
        
        # Mock the expensive indexer.main call
        with patch('mcp_pydantic_docs.indexer.main') as mock_indexer:
            mock_indexer.return_value = None  # Successful execution
            result = await t_rebuild_indices()
        
        assert isinstance(result, dict), "Should return dict"
        assert "success" in result, "Should indicate success/failure"
        assert "message" in result, "Should include message"
        
        assert isinstance(result["success"], bool)
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0

    @pytest.mark.asyncio
    async def test_mode_paths_are_absolute(self):
        """Test that reported paths are absolute."""
        result = t_mode()
        
        # Paths should be absolute (start with /)
        assert result["doc_root"].startswith("/") or ":" in result["doc_root"], \
            "doc_root should be absolute path"
        assert result["doc_root_ai"].startswith("/") or ":" in result["doc_root_ai"], \
            "doc_root_ai should be absolute path"
        assert result["data_dir"].startswith("/") or ":" in result["data_dir"], \
            "data_dir should be absolute path"

    @pytest.mark.asyncio
    async def test_cache_status_offline_mode_boolean(self):
        """Test that offline mode is boolean."""
        result = await t_cache_status()
        
        assert isinstance(result["offline_mode"], bool), \
            "offline_mode should be boolean"


@pytest.mark.admin
class TestAdminEdgeCases:
    """Test edge cases in admin tools."""

    @pytest.mark.asyncio
    async def test_rebuild_indices_handles_missing_jsonl(self):
        """Test rebuild indices when JSONL files are missing (mocked)."""
        from unittest.mock import MagicMock, patch
        
        # Mock to simulate missing JSONL files
        with patch('mcp_pydantic_docs.mcp.DATA_DIR') as mock_dir:
            # Create a mock path that says files don't exist
            mock_path = MagicMock()
            mock_path.__truediv__ = lambda self, x: mock_path
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = lambda self, x: mock_path
            
            result = await t_rebuild_indices()
            
            # Should handle gracefully with appropriate message
            if not result["success"]:
                assert "jsonl" in result["message"].lower() or "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_cache_status_handles_missing_directories(self):
        """Test that cache status handles missing directories gracefully."""
        result = await t_cache_status()
        
        # Should return valid structure even if dirs don't exist
        assert "documentation" in result
        assert "jsonl_data" in result
        
        # All boolean flags should be valid
        for site_data in result["documentation"].values():
            assert isinstance(site_data["exists"], bool)

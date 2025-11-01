"""Tests for health check tools."""

from __future__ import annotations

import pytest

from mcp_pydantic_docs.mcp import ping, validate


@pytest.mark.health
class TestHealthChecks:
    """Test health check functionality."""

    def test_ping_returns_pong(self):
        """Test that ping returns 'pong'."""
        result = ping()
        assert result == "pong", "ping() should return 'pong'"

    def test_validate_returns_dict(self, skip_if_no_indices):
        """Test that validate returns a dictionary."""
        result = validate()
        assert isinstance(result, dict), "validate() should return a dict"

    def test_validate_has_required_keys(self, skip_if_no_indices):
        """Test that validate response has required keys."""
        result = validate()
        required_keys = ["valid", "message", "bm25_present", "records_present"]
        for key in required_keys:
            assert key in result, f"validate() response missing key: {key}"

    def test_validate_indices_valid(self, skip_if_no_indices):
        """Test that validation passes when indices exist."""
        result = validate()
        assert result["valid"] is True, "Indices should be valid"
        assert result["bm25_present"] is True, "BM25 index should be present"
        assert result["records_present"] is True, "Records should be present"

    def test_validate_has_size_info(self, skip_if_no_indices):
        """Test that validate returns size information."""
        result = validate()
        assert "bm25_size_mb" in result, "Missing BM25 size info"
        assert "records_size_mb" in result, "Missing records size info"
        
        assert isinstance(result["bm25_size_mb"], (int, float)), "BM25 size should be numeric"
        assert isinstance(result["records_size_mb"], (int, float)), "Records size should be numeric"
        
        assert result["bm25_size_mb"] > 0, "BM25 size should be positive"
        assert result["records_size_mb"] > 0, "Records size should be positive"

    def test_validate_message_informative(self, skip_if_no_indices):
        """Test that validate message is informative."""
        result = validate()
        assert len(result["message"]) > 0, "Message should not be empty"
        assert isinstance(result["message"], str), "Message should be a string"

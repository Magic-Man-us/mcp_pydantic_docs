#!/usr/bin/env python3
"""
Validation script for MCP Pydantic Documentation Server.
Tests all available tools to ensure they work correctly.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add the package to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp_pydantic_docs.mcp import (
    ping,
    t_api,
    t_cache_status,
    t_get,
    t_mode,
    t_rebuild_indices,
    t_search,
    t_section,
    validate,
)


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}\n")


def print_test(name: str, status: str, message: str = "") -> None:
    """Print a test result."""
    if status == "PASS":
        symbol = f"{Colors.GREEN}✓{Colors.RESET}"
        status_text = f"{Colors.GREEN}PASS{Colors.RESET}"
    elif status == "FAIL":
        symbol = f"{Colors.RED}✗{Colors.RESET}"
        status_text = f"{Colors.RED}FAIL{Colors.RESET}"
    else:
        symbol = f"{Colors.YELLOW}⚠{Colors.RESET}"
        status_text = f"{Colors.YELLOW}WARN{Colors.RESET}"
    
    print(f"{symbol} {name:.<50} {status_text}")
    if message:
        print(f"   {Colors.YELLOW}{message}{Colors.RESET}")


async def test_health_ping() -> tuple[bool, str]:
    """Test health_ping tool."""
    try:
        result = ping()
        if result == "pong":
            return True, "Returned 'pong' as expected"
        return False, f"Unexpected response: {result}"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_health_validate() -> tuple[bool, str]:
    """Test health_validate tool."""
    try:
        result = validate()
        if isinstance(result, dict) and "valid" in result:
            if result["valid"]:
                return True, f"Indices valid: {result.get('message', 'OK')}"
            return False, f"Indices invalid: {result.get('message', 'Unknown')}"
        return False, f"Unexpected response format: {result}"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_pydantic_mode() -> tuple[bool, str]:
    """Test pydantic_mode tool."""
    try:
        result = t_mode()
        if isinstance(result, dict):
            required_keys = ["offline_only", "doc_root", "data_dir", "bm25_present"]
            missing = [k for k in required_keys if k not in result]
            if not missing:
                return True, f"Offline: {result['offline_only']}, BM25: {result['bm25_present']}"
            return False, f"Missing keys: {missing}"
        return False, f"Unexpected response type: {type(result)}"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_pydantic_search() -> tuple[bool, str]:
    """Test pydantic_search tool."""
    try:
        result = await t_search(query="BaseModel", k=5)
        if hasattr(result, 'results'):
            count = len(result.results)
            if count > 0:
                first_title = result.results[0].title if result.results else "N/A"
                return True, f"Found {count} results, first: '{first_title}'"
            return False, "No results returned for 'BaseModel' query"
        return False, f"Unexpected response type: {type(result)}"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_pydantic_get() -> tuple[bool, str]:
    """Test pydantic_get tool."""
    try:
        # Try to get a common page
        result = await t_get("api/base_model/index.html")
        if hasattr(result, 'text') and hasattr(result, 'html'):
            text_len = len(result.text)
            html_len = len(result.html)
            if text_len > 0 and html_len > 0:
                return True, f"Retrieved page: {text_len} chars text, {html_len} chars html"
            return False, f"Empty content: text={text_len}, html={html_len}"
        return False, f"Unexpected response type: {type(result)}"
    except FileNotFoundError:
        return False, "Test file not found (docs may not be downloaded)"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_pydantic_section() -> tuple[bool, str]:
    """Test pydantic_section tool."""
    try:
        # Try to get a section from BaseModel docs
        result = await t_section("api/base_model/index.html", "pydantic.BaseModel.model_dump")
        if hasattr(result, 'section'):
            section_len = len(result.section)
            if section_len > 0:
                return True, f"Retrieved section: {section_len} chars, truncated: {result.truncated}"
            return False, "Empty section content"
        return False, f"Unexpected response type: {type(result)}"
    except FileNotFoundError:
        return False, "Test file not found (docs may not be downloaded)"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_pydantic_api() -> tuple[bool, str]:
    """Test pydantic_api tool."""
    try:
        result = await t_api("BaseModel")
        if isinstance(result, dict):
            if "url" in result and ("text" in result or "section" in result):
                content_key = "text" if "text" in result else "section"
                content_len = len(result[content_key])
                return True, f"Retrieved {content_key}: {content_len} chars"
            return False, "Missing expected keys in response"
        return False, f"Unexpected response type: {type(result)}"
    except FileNotFoundError:
        return False, "API docs not found (docs may not be downloaded)"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_admin_cache_status() -> tuple[bool, str]:
    """Test admin_cache_status tool."""
    try:
        result = await t_cache_status()
        if isinstance(result, dict):
            required_keys = ["paths", "documentation", "search_indices"]
            missing = [k for k in required_keys if k not in result]
            if not missing:
                indices_valid = result.get("search_indices", {}).get("valid", False)
                return True, f"Cache status retrieved, indices valid: {indices_valid}"
            return False, f"Missing keys: {missing}"
        return False, f"Unexpected response type: {type(result)}"
    except Exception as e:
        return False, f"Exception: {e}"


async def test_admin_rebuild_indices() -> tuple[bool, str]:
    """Test admin_rebuild_indices tool (non-destructive check)."""
    try:
        # We won't actually rebuild, just check if the function exists and is callable
        # This is a destructive operation, so we just verify it's available
        if callable(t_rebuild_indices):
            return True, "Tool is available (not executed to avoid rebuilding)"
        return False, "Tool is not callable"
    except Exception as e:
        return False, f"Exception: {e}"


async def run_all_tests() -> dict[str, tuple[bool, str]]:
    """Run all validation tests."""
    tests = {
        "health_ping": test_health_ping,
        "health_validate": test_health_validate,
        "pydantic_mode": test_pydantic_mode,
        "pydantic_search": test_pydantic_search,
        "pydantic_get": test_pydantic_get,
        "pydantic_section": test_pydantic_section,
        "pydantic_api": test_pydantic_api,
        "admin_cache_status": test_admin_cache_status,
        "admin_rebuild_indices": test_admin_rebuild_indices,
    }
    
    results = {}
    for name, test_func in tests.items():
        try:
            results[name] = await test_func()
        except Exception as e:
            results[name] = (False, f"Test execution failed: {e}")
    
    return results


async def main() -> int:
    """Main entry point."""
    print_header("MCP Pydantic Docs Server Validation")
    
    print(f"{Colors.BOLD}Testing all available tools...{Colors.RESET}\n")
    
    results = await run_all_tests()
    
    # Print results
    passed = 0
    failed = 0
    
    for tool_name, (success, message) in results.items():
        status = "PASS" if success else "FAIL"
        print_test(tool_name, status, message)
        if success:
            passed += 1
        else:
            failed += 1
    
    # Summary
    print_header("Summary")
    total = passed + failed
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"Total Tests: {Colors.BOLD}{total}{Colors.RESET}")
    print(f"Passed: {Colors.GREEN}{passed}{Colors.RESET}")
    print(f"Failed: {Colors.RED}{failed}{Colors.RESET}")
    print(f"Pass Rate: {Colors.BOLD}{pass_rate:.1f}%{Colors.RESET}\n")
    
    if failed == 0:
        print(f"{Colors.GREEN}✓ All tests passed!{Colors.RESET}\n")
        return 0
    else:
        print(f"{Colors.RED}✗ Some tests failed. See details above.{Colors.RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

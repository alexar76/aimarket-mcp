"""Stdio MCP smoke — Glama entrypoint imports and exposes the three gateway tools."""
from __future__ import annotations

import importlib


def test_stdio_module_imports():
    mod = importlib.import_module("mcp_stdio_server")
    assert hasattr(mod, "mcp")
    assert hasattr(mod, "main")


def test_stdio_tools_registered():
    import mcp_stdio_server as stdio

    tools = stdio.mcp._tool_manager._tools  # FastMCP internal registry
    names = set(tools.keys())
    assert {"web_fetch_tool", "web_search_tool", "metis_verify_tool"} <= names

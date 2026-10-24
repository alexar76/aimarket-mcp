"""Stdio MCP smoke — Glama entrypoint exposes the complete gateway catalog."""
from __future__ import annotations

import importlib


def test_stdio_module_imports():
    mod = importlib.import_module("aimarket_mcp.stdio_server")
    assert hasattr(mod, "mcp")
    assert hasattr(mod, "main")


def test_stdio_tools_registered():
    from aimarket_mcp import stdio_server as stdio

    tools = stdio.mcp._tool_manager._tools  # FastMCP internal registry
    names = set(tools.keys())
    # The same names the HTTP gateway, the README and every tool description use: a
    # description that says "call market_search first" must name a tool that exists here.
    assert names == {
        "web_fetch", "web_search", "metis_verify",
        "market_search", "market_invoke", "market_status",
    }


def test_every_stdio_tool_has_a_title_hints_and_the_shared_description():
    from aimarket_mcp import stdio_server as stdio
    from aimarket_mcp.tools import TOOLS_BY_NAME

    for name, tool in stdio.mcp._tool_manager._tools.items():
        assert tool.description == TOOLS_BY_NAME[name]["description"], name
        ann = tool.annotations
        assert ann is not None and ann.title, name
        assert ann.destructiveHint is False, name
        # Only market_invoke can act or spend; everything else only reads.
        assert ann.readOnlyHint is (name != "market_invoke"), name



def test_market_status_reports_trial_and_balance_without_the_key(monkeypatch):
    import asyncio
    import json

    import httpx
    from aimarket_mcp import tools

    seen = []

    async def fake_get(url, *, headers=None, **_):
        seen.append((url, dict(headers or {})))
        if url.endswith("/ai-market/v2/health"):
            return httpx.Response(200, json={"status": "ok"})
        if "/sandbox/quota?" in url:
            return httpx.Response(200, json={"enabled": True, "remaining": 2, "max_trials": 5, "used": 3, "quota_window": "hourly"})
        if url.endswith("/ai-market/v2/account"):
            return httpx.Response(200, json={"balance_usd": 0.42})
        return httpx.Response(404, json={})

    monkeypatch.setattr(tools, "safe_get", fake_get)
    monkeypatch.setattr(tools, "API_KEY", "aimk_secret_value")
    out = asyncio.run(tools.market_status({}))
    assert "aimk_secret_value" not in out
    body = json.loads(out[out.index("{"):out.rindex("}") + 1])
    assert body["hub_status"] == "ok"
    assert body["free_trial"]["remaining"] == 2
    assert body["prepaid_balance_usd"] == 0.42
    assert body["api_key_configured"] is True
    quota_url = next(u for u, _ in seen if "/sandbox/quota?" in u)
    assert "visitor_id=" in quota_url
    assert next(h for u, h in seen if u.endswith("/account"))["X-API-Key"] == "aimk_secret_value"

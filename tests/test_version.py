"""One version number, everywhere a client or a registry can read it.

0.3.0 shipped to PyPI announcing `serverInfo.version: 0.2.3` — the same drift __init__.py
already documented for 0.1.x. scripts/prerelease.py checks this, but only when someone runs
it, and 0.3.0 was uploaded without it. Here it fails every test run instead.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from aimarket_mcp import __version__, server
from aimarket_mcp import stdio_server

ROOT = Path(__file__).resolve().parent.parent


def _declared() -> str:
    # Regex, not tomllib: requires-python is >=3.10 and tomllib is 3.11+.
    m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    assert m, "no version in pyproject.toml"
    return m.group(1)


def test_package_version_matches_pyproject():
    assert __version__ == _declared()


def test_registry_manifest_matches_pyproject():
    manifest = json.loads((ROOT / "server.json").read_text())
    assert manifest["version"] == _declared()
    for pkg in manifest["packages"]:
        assert pkg["version"] == _declared(), pkg["identifier"]


async def test_http_serverinfo_and_health_announce_pyproject_version():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),
                                 base_url="http://t") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                       "params": {"protocolVersion": "2025-03-26"}})
        frame = next(line for line in r.text.splitlines() if line.startswith("data:"))
        assert json.loads(frame[5:])["result"]["serverInfo"]["version"] == _declared()
        assert (await c.get("/health")).json()["version"] == _declared()


def test_stdio_serverinfo_announces_pyproject_version():
    # What the lowlevel Server hands the client in the initialize result.
    opts = stdio_server.mcp._mcp_server.create_initialization_options()
    assert opts.server_version == _declared()

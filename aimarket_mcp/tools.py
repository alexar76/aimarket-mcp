"""Ecosystem MCP tools. Each is a real handler over a real backend, hardened by security.py.

Namespaces:
  web_fetch     — fetch a URL and return its main text (SSRF-guarded, sanitized)
  web_search    — live DuckDuckGo search, top snippets (sanitized)
  metis_verify  — run Metis's cognition/verification envelope on an input (confidence score)
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from .security import safe_get, safe_post, sanitize_tool_output, extract_main_text, validate_url

DDG_URL = os.environ.get("AIMARKET_SEARCH_URL", "https://html.duckduckgo.com/html/")
METIS_URL = os.environ.get("AIMARKET_METIS_URL", "https://metis.modelmarket.dev").rstrip("/")
METIS_KEY = os.environ.get("AIMARKET_METIS_KEY", "")


async def web_fetch(args: Dict[str, Any]) -> str:
    url = str(args.get("url", "")).strip()
    if not url:
        raise ValueError("web_fetch requires 'url'")
    validate_url(url)  # explicit pre-check for a clean error
    resp = await safe_get(url, headers={"User-Agent": "aimarket-mcp/0.1 (+https://modelmarket.dev)"})
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "html" in ctype or "<html" in resp.text[:2000].lower():
        text = extract_main_text(resp.text, max_chars=int(args.get("max_chars", 20000)))
    else:
        text = resp.text[: int(args.get("max_chars", 20000))]
    return sanitize_tool_output(f"# {url}\n\n{text}")


async def web_search(args: Dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()[:500]
    if not query:
        raise ValueError("web_search requires 'query'")
    resp = await safe_post(DDG_URL, data={"q": query}, headers={"User-Agent": "aimarket-mcp/0.1"})
    resp.raise_for_status()
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)[:6]
    clean = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets]
    out = "\n".join(f"- {s}" for s in clean if s) or "No results found."
    return sanitize_tool_output(out)


async def metis_verify(args: Dict[str, Any]) -> str:
    inp = str(args.get("input", "")).strip()
    if not inp:
        raise ValueError("metis_verify requires 'input'")
    route = str(args.get("route", "council"))
    headers = {"Content-Type": "application/json"}
    if METIS_KEY:
        headers["Authorization"] = f"Bearer {METIS_KEY}"
    resp = await safe_post(f"{METIS_URL}/v1/verify", json={"input": inp, "route": route},
                           headers=headers, timeout=200.0)
    resp.raise_for_status()
    d = resp.json()
    answer = d.get("answer", "")
    meta = (f"[verify_score={d.get('verify_score')} status={d.get('status')} "
            f"route={d.get('route')} verified={d.get('verified')}]")
    # answer is Metis's own output (trusted tier), meta is machine-readable — no <untrusted> wrap
    return f"{answer}\n\n{meta}"


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "web_fetch",
        "description": (
            "Fetch a public http(s) page by URL and return its main text (readability-lite). "
            "SSRF-hardened: scheme allow-list, private-IP/localhost block, per-redirect "
            "re-validation, response size cap. Output is sanitized, forged role markers stripped, "
            "and wrapped in <untrusted>…</untrusted> before model consumption."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Public http(s) URL. Example: https://example.com/docs/guide",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters of extracted main text (default 20000, max 100000).",
                },
            },
            "required": ["url"],
        },
        "handler": web_fetch,
    },
    {
        "name": "web_search",
        "description": (
            "Search the live web (DuckDuckGo HTML) for current facts and return top snippet "
            "summaries. Output is sanitized and wrapped <untrusted> like web_fetch. Use when the "
            "answer depends on recent documentation, releases, or news."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query (max 500 chars).",
                },
            },
            "required": ["query"],
        },
        "handler": web_search,
    },
    {
        "name": "metis_verify",
        "description": (
            "Run Metis cognition + verification envelope on an input via /v1/verify. Returns the "
            "answer plus machine-readable verify_score, status, route, and verified flag so agents "
            "can fail-closed when confidence is insufficient. Configure AIMARKET_METIS_URL and "
            "optional AIMARKET_METIS_KEY."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Question or task for Metis to answer and verify.",
                },
                "route": {
                    "type": "string",
                    "enum": ["fast", "thinking", "council", "agent"],
                    "description": (
                        "Cognition depth: fast, thinking, council (default), or agent (tool-using)."
                    ),
                },
            },
            "required": ["input"],
        },
        "handler": metis_verify,
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}

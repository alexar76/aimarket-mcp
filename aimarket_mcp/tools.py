"""Ecosystem MCP tools. Each is a real handler over a real backend, hardened by security.py.

Namespaces:
  web_fetch      — fetch a URL and return its main text (SSRF-guarded, sanitized)
  web_search     — live DuckDuckGo search, top snippets (sanitized)
  metis_verify   — run Metis's cognition/verification envelope on an input (confidence score)
  market_search  — discover priced capabilities on an AIMarket hub
  market_invoke  — run one, on the hub's free trial tier, and return the signed receipt
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import uuid
from typing import Any, Dict, List

from . import __version__
from .security import safe_get, safe_post, sanitize_tool_output, extract_main_text, validate_url

# One User-Agent for every outbound call, carrying the real package version so a hub's
# logs can tell which release is talking to them. Was three hardcoded "0.1" strings.
_UA = f"aimarket-mcp/{__version__} (+https://modelmarket.dev)"

DDG_URL = os.environ.get("AIMARKET_SEARCH_URL", "https://html.duckduckgo.com/html/")
METIS_URL = os.environ.get("AIMARKET_METIS_URL", "https://metis.modelmarket.dev").rstrip("/")
METIS_KEY = os.environ.get("AIMARKET_METIS_KEY", "")
HUB_URL = os.environ.get("AIMARKET_HUB_URL", "https://modelmarket.dev").rstrip("/")
# Identifies this installation to the hub's trial ledger, which allows a few free
# invokes per visitor. Random per-install rather than shared, so one heavy user cannot
# consume everyone else's allowance; override to keep an allowance across reinstalls.
def _visitor_id() -> str:
    """Trial identity for this installation.

    The hub requires 8-64 chars of [A-Za-z0-9_-]; a shorter override is refused, and the
    refusal used to arrive as `missing_visitor_id`. Pad rather than fail so someone who
    sets AIMARKET_SANDBOX_VISITOR=me still gets a working, stable identity.
    """
    raw = "".join(c for c in (os.environ.get("AIMARKET_SANDBOX_VISITOR") or "") if c.isalnum() or c in "_-")
    if len(raw) >= 8:
        return raw[:64]
    return f"mcp-{raw}-{uuid.uuid4().hex[:12]}"[:64] if raw else f"mcp-{uuid.uuid4().hex[:12]}"


SANDBOX_VISITOR = _visitor_id()


async def web_fetch(args: Dict[str, Any]) -> str:
    url = str(args.get("url", "")).strip()
    if not url:
        raise ValueError("web_fetch requires 'url'")
    validate_url(url)  # explicit pre-check for a clean error
    resp = await safe_get(url, headers={"User-Agent": _UA})
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
    resp = await safe_post(DDG_URL, data={"q": query}, headers={"User-Agent": _UA})
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


async def market_search(args: Dict[str, Any]) -> str:
    """Search the hub catalogue. Free — no wallet, no channel, no key."""
    intent = str(args.get("intent", "")).strip()[:500]
    if not intent:
        raise ValueError("market_search requires 'intent'")
    params = {"intent": intent, "limit": str(min(int(args.get("limit", 10) or 10), 25))}
    if args.get("category"):
        params["category"] = str(args["category"])[:64]
    if args.get("max_price_usd") is not None:
        params["budget"] = str(args["max_price_usd"])
    resp = await safe_get(
        f"{HUB_URL}/ai-market/v2/search?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": _UA},
    )
    resp.raise_for_status()
    matches = (resp.json() or {}).get("matches") or []
    if not matches:
        return sanitize_tool_output(
            f"No capability on {HUB_URL} matches {intent!r}. The hub only lists what it can "
            f"actually execute, so an empty result means it is genuinely not for sale here."
        )
    lines = [f"{len(matches)} capability(ies) on {HUB_URL}:"]
    for m in matches:
        hub = str(m.get("source_hub") or "")
        # Surfaced because market_invoke needs it verbatim for anything the hub does not
        # execute itself: a federated capability invoked without source_hub falls through
        # to the local factory path and answers 404.
        origin = "" if hub in ("", "local") else f"  source_hub={hub}"
        lines.append(
            f"- {m.get('capability_id')}  ${m.get('price_per_call_usd')}/call"
            f"  product_id={m.get('product_id')}  trust={m.get('trust_score')}{origin}"
            f"  {(m.get('name') or '')[:60]}"
        )
    lines.append(
        "\nCall market_invoke with capability_id + product_id, and source_hub too when "
        "one is shown above."
    )
    return sanitize_tool_output("\n".join(lines))


async def market_invoke(args: Dict[str, Any]) -> str:
    """Invoke a capability on the hub's free trial tier.

    Deliberately does NOT take a payment channel or a key. The hub grants a few trial
    invokes per visitor, which is enough to see whether a capability is worth paying
    for; when the allowance runs out it answers 402 and this returns that verdict
    verbatim rather than inventing a result. Paying requires an on-chain escrow deposit,
    which belongs to the operator's wallet, not to an MCP tool.
    """
    capability_id = str(args.get("capability_id", "")).strip()
    if not capability_id:
        raise ValueError("market_invoke requires 'capability_id' (see market_search)")
    product_id = str(args.get("product_id", "")).strip() or capability_id.split(".", 1)[0]
    payload = args.get("input")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"input": payload}
    body = {
        "product_id": product_id,
        "capability_id": capability_id,
        "input": payload if isinstance(payload, dict) else {},
    }
    # Required for federated capabilities — most of the catalogue. The hub only takes the
    # peer transport when source_hub names a known peer; without it the invoke goes down
    # the local factory path and returns 404 for everything the hub does not host itself.
    source_hub = str(args.get("source_hub") or "").strip()
    if source_hub and source_hub != "local":
        body["source_hub"] = source_hub
    resp = await safe_post(
        f"{HUB_URL}/ai-market/v2/invoke",
        json=body,
        headers={
            "content-type": "application/json",
            "X-AIMarket-Sandbox-Visitor": SANDBOX_VISITOR,
            "User-Agent": _UA,
        },
    )
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code == 402:
        return sanitize_tool_output(
            f"{capability_id} needs payment: the free trial allowance for this installation is "
            f"used up. The hub's answer: {json.dumps(body)[:400]}\n"
            f"Paid access means opening an AIMarketEscrow channel on Base and passing its id — "
            f"an operator action with a funded wallet, not something this tool can do."
        )
    if resp.status_code >= 400:
        return sanitize_tool_output(
            f"{capability_id} refused with HTTP {resp.status_code}: {json.dumps(body)[:400]}"
        )
    out = {
        "capability_id": capability_id,
        "success": body.get("success"),
        # Two shapes: the local path answers `result`, the federated path answers `output`.
        # Reading only `result` reported `"result": null` for every federated capability —
        # which, once the oracle family was indexed, is most of the catalogue.
        "result": body.get("result") if body.get("result") is not None else body.get("output"),
        "sandbox": body.get("sandbox"),
        # The receipt is the point: a signed statement of what ran, verifiable against
        # the hub's published key, so the caller need not trust this transcript.
        "receipt_nonce": (body.get("receipt") or {}).get("nonce"),
    }
    return sanitize_tool_output(json.dumps(out, ensure_ascii=False, indent=2)[:20000])


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
    {
        "name": "market_search",
        "description": (
            "Discover paid AI capabilities listed on an AIMarket hub (default "
            "https://modelmarket.dev) by natural-language intent. Returns capability_id, "
            "product_id, price per call in USD and a trust score. Free: no wallet, key or "
            "channel. The hub lists only capabilities it can actually execute, so an empty "
            "result means it genuinely does not sell that. Point elsewhere with AIMARKET_HUB_URL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "What you want done, in plain language (max 500 chars).",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter, e.g. 'security'.",
                },
                "max_price_usd": {
                    "type": "number",
                    "description": "Optional cap: hide capabilities dearer than this per call.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results, capped at 25 (default 10).",
                },
            },
            "required": ["intent"],
        },
        "handler": market_search,
    },
    {
        "name": "market_invoke",
        "description": (
            "Run one capability found via market_search, on the hub's free trial tier, and "
            "return its output plus the nonce of the hub-signed receipt. A few trial invokes "
            "are granted per installation; after that the hub answers 402 and this reports "
            "that instead of fabricating a result. Paid access needs an on-chain escrow "
            "deposit, which is an operator action and deliberately out of scope here."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "capability_id": {
                    "type": "string",
                    "description": "Exact capability_id from market_search, e.g. 'skopos.fleet.status@v1'.",
                },
                "product_id": {
                    "type": "string",
                    "description": (
                        "The product_id from market_search, e.g. 'prod-skopos'. Inferred from "
                        "the capability_id prefix when omitted, which is often wrong — pass it."
                    ),
                },
                "source_hub": {
                    "type": "string",
                    "description": (
                        "The source_hub from market_search, when it showed one. Required for "
                        "federated capabilities — which is most of the catalogue; omitting it "
                        "makes the hub look for the capability locally and answer 404."
                    ),
                },
                "input": {
                    "type": "object",
                    "description": "Input object for the capability; {} when it takes none.",
                },
            },
            "required": ["capability_id"],
        },
        "handler": market_invoke,
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}

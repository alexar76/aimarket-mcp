"""aimarket-mcp — the ecosystem MCP gateway.

Speaks MCP over Streamable-HTTP (JSON-RPC 2.0 POST, SSE-`data:`-framed response,
Mcp-Session-Id header) — the exact protocol Metis's MCP client and ARGUS already talk, so
no external SDK is needed. Every tool call runs behind the vendored security core
(SSRF + output sanitization) and optional bearer auth.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any, Dict

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .tools import TOOLS, TOOLS_BY_NAME

SERVER_NAME = "aimarket-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-03-26"

_API_KEY = os.environ.get("AIMARKET_MCP_KEY", "")
_PRODUCTION = os.environ.get("AIMARKET_MCP_PRODUCTION", "").lower() in ("1", "true", "yes")
# rate limit: token bucket per client key/IP
_RL_PER_MIN = int(os.environ.get("AIMARKET_MCP_RATE", "120"))
_buckets: Dict[str, list] = {}


def _sse(payload: Dict[str, Any], *, session_id: str | None = None) -> Response:
    body = f"event: message\ndata: {json.dumps(payload)}\n\n"
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return Response(body, media_type="text/event-stream", headers=headers)


def _err(req_id, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _ok(req_id, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _auth_ok(request: Request) -> bool:
    # fail-closed like metis: if a key is configured (or production), require a matching bearer
    if not _API_KEY:
        return not _PRODUCTION
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    return secrets.compare_digest(header[7:].strip(), _API_KEY)


def _rate_ok(key: str) -> bool:
    now = time.monotonic()
    window = _buckets.setdefault(key, [])
    cutoff = now - 60.0
    window[:] = [t for t in window if t > cutoff]
    if len(window) >= _RL_PER_MIN:
        return False
    window.append(now)
    # opportunistic cleanup so the dict can't grow unbounded
    if len(_buckets) > 4096:
        for k in [k for k, v in _buckets.items() if not v or v[-1] < cutoff]:
            _buckets.pop(k, None)
    return True


async def handle_rpc(request: Request) -> Response:
    if not _auth_ok(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    client_key = request.headers.get("authorization", "") or (request.client.host if request.client else "anon")
    if not _rate_ok(client_key[:64]):
        return JSONResponse({"error": "rate limited"}, status_code=429)

    try:
        msg = await request.json()
    except Exception:
        return _sse(_err(None, -32700, "Parse error"))

    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    # notifications carry no id and expect no body
    if req_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return Response(status_code=202)

    if method == "initialize":
        sid = secrets.token_hex(16)
        return _sse(_ok(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }), session_id=sid)

    if method == "ping":
        return _sse(_ok(req_id, {}))

    if method == "tools/list":
        tools = [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
                 for t in TOOLS]
        return _sse(_ok(req_id, {"tools": tools}))

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        tool = TOOLS_BY_NAME.get(name)
        if not tool:
            return _sse(_err(req_id, -32602, f"Unknown tool: {name}"))
        try:
            text = await tool["handler"](arguments)
            return _sse(_ok(req_id, {"content": [{"type": "text", "text": text}], "isError": False}))
        except Exception as e:  # tool failure is returned as an isError result, not a transport error
            return _sse(_ok(req_id, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                                     "isError": True}))

    return _sse(_err(req_id, -32601, f"Method not found: {method}"))


async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok", "service": SERVER_NAME, "version": SERVER_VERSION,
                         "tools": [t["name"] for t in TOOLS], "auth": bool(_API_KEY)})


app = Starlette(routes=[
    Route("/health", health, methods=["GET"]),
    Route("/", handle_rpc, methods=["POST"]),
    Route("/mcp", handle_rpc, methods=["POST"]),
])


def main() -> None:
    import uvicorn
    port = int(os.environ.get("AIMARKET_MCP_PORT", "9090"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

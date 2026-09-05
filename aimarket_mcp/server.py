"""aimarket-mcp — the ecosystem MCP gateway.

Speaks MCP over Streamable-HTTP (JSON-RPC 2.0 POST, SSE-`data:`-framed response,
Mcp-Session-Id header) — the exact protocol Metis's MCP client and ARGUS already talk, so
no external SDK is needed. Every tool call runs behind the vendored security core
(SSRF + output sanitization) and optional bearer auth.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from typing import Any, Dict

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from . import __version__
from .tools import TOOLS, TOOLS_BY_NAME, bind_visitor, release_visitor

SERVER_NAME = "aimarket-mcp"
SERVER_VERSION = __version__
PROTOCOL_VERSION = "2025-03-26"

_API_KEY = os.environ.get("AIMARKET_MCP_KEY", "")


def _is_production() -> bool:
    # Honour both the MCP-specific marker and the ecosystem-wide markers so a standard
    # prod deploy (AIFACTORY_PROD=1) fails closed even without AIMARKET_MCP_PRODUCTION —
    # matches security/prod_startup_guard.is_production_mode.
    if os.environ.get("AIFACTORY_ENV", "").strip().lower() in ("production", "prod", "live"):
        return True
    for key in ("AIMARKET_MCP_PRODUCTION", "AIFACTORY_PROD", "AIFACTORY_PRODUCTION"):
        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


_PRODUCTION = _is_production()

# A public deployment is a deliberate act, never a default. Production still fails closed
# without a bearer key (see _auth_ok); AIMARKET_MCP_PUBLIC=1 is the explicit opt-in that
# lets the hosted endpoint at https://modelmarket.dev/mcp answer anonymous callers, which
# is the entire point of a "paste one URL into your MCP client" listing.
_PUBLIC = os.environ.get("AIMARKET_MCP_PUBLIC", "").strip().lower() in ("1", "true", "yes", "on")


def _parse_trusted(raw: str) -> list:
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part == "*":
            return ["*"]
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


# Which peers may speak for someone else — loopback only, because a trusted peer can hand
# us any client address it likes and the trial allowance is keyed on that address. Trusting
# the private ranges by default would extend that to every host on the same LAN, VPC or
# docker bridge, which is not a set of machines this process knows anything about.
# In a container the peer is the bridge gateway, so a containerised deployment behind nginx
# must name it: AIMARKET_MCP_TRUSTED_PROXIES=172.17.0.1 (or the CIDR of that bridge).
_TRUSTED_PROXIES = _parse_trusted(
    os.environ.get("AIMARKET_MCP_TRUSTED_PROXIES", "127.0.0.1/32,::1/128")
)

# Salt for the visitor digest, so the hub's trial ledger never receives a raw client IP.
# Ephemeral by default: a restart re-rolls it and everyone's allowance starts over, which
# is the forgiving direction to fail. Pin it to keep allowances across restarts.
_VISITOR_SALT = os.environ.get("AIMARKET_MCP_VISITOR_SALT", "") or secrets.token_hex(16)

# rate limit: token bucket per client key/IP
_RL_PER_MIN = int(os.environ.get("AIMARKET_MCP_RATE", "120"))
_buckets: Dict[str, list] = {}


def _peer_is_trusted(peer: str) -> bool:
    if _TRUSTED_PROXIES == ["*"]:
        return True
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_PROXIES)


def _client_ip(request: Request) -> str:
    """The caller's own address, as far as it can be trusted.

    Behind nginx every peer is the proxy itself, so keying anything on `request.client`
    collapses the whole internet into one bucket — one caller could then exhaust the
    global rate limit and the trial allowance for everybody. Forwarding headers are read
    only from a trusted peer, and X-Forwarded-For is read from the RIGHT: nginx appends
    the address it actually saw, so the rightmost hop is the one entry a client cannot
    forge by sending a header of its own.
    """
    peer = request.client.host if request.client else ""
    if not peer or not _peer_is_trusted(peer):
        return peer or "anon"
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    # Only when there is no forwarded chain at all. X-Real-IP is a single-value header that
    # nginx overwrites but that other fronts pass through verbatim, so a caller who sends
    # one must not be able to outrank the append-only chain above — preferring it was worth
    # a fresh trial allowance per request.
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real
    return peer


def _visitor_for(request: Request, session_id: str = "") -> str:
    """Per-caller trial identity: opaque, stable, and never the raw client address.

    Keyed on the client IP because rotating one costs an attacker something, while
    rotating an MCP session id costs nothing. Callers with no usable address (direct,
    unproxied peers) fall back to their session so they are not merged into one bucket.
    """
    basis = _client_ip(request)
    if basis in ("", "anon"):
        basis = f"session:{session_id or 'none'}"
    digest = hmac.new(_VISITOR_SALT.encode(), basis.encode(), hashlib.sha256).hexdigest()
    return f"mcpx-{digest[:24]}"


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
        return _PUBLIC or not _PRODUCTION
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
    # The bearer only identifies a caller when it was actually checked. In public mode
    # _auth_ok never reads it, so keying the limiter on it would hand a fresh bucket to
    # anyone willing to send a new random token per request — and grow _buckets by one
    # entry each time. Authenticated deployments still get per-key buckets.
    client_key = (request.headers.get("authorization", "") if _API_KEY else "") or _client_ip(request)
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
        # Each request runs in its own task, so the bound identity cannot leak into a
        # concurrent caller's invoke; released explicitly so a reused task cannot inherit it.
        token = bind_visitor(_visitor_for(request, request.headers.get("mcp-session-id", "")))
        try:
            text = await tool["handler"](arguments)
            return _sse(_ok(req_id, {"content": [{"type": "text", "text": text}], "isError": False}))
        except Exception as e:  # tool failure is returned as an isError result, not a transport error
            return _sse(_ok(req_id, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                                     "isError": True}))
        finally:
            release_visitor(token)

    return _sse(_err(req_id, -32601, f"Method not found: {method}"))


async def handle_get(request: Request) -> Response:
    """No server-initiated SSE stream here — the spec's answer for that is 405, not 404.

    Clients probe GET before falling back to POST-only; a 404 reads as "wrong URL" and
    some of them abandon the endpoint, so the refusal has to be the specified one.
    """
    return JSONResponse(
        {"error": "This endpoint answers MCP over JSON-RPC POST; it offers no server-initiated stream."},
        status_code=405,
        headers={"Allow": "POST, DELETE"},
    )


async def handle_delete(request: Request) -> Response:
    # Sessions carry no server-side state, so honouring a client's termination is a no-op
    # that still has to succeed — clients treat an error here as a broken connection.
    return Response(status_code=204)


async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok", "service": SERVER_NAME, "version": SERVER_VERSION,
                         "tools": [t["name"] for t in TOOLS], "auth": bool(_API_KEY),
                         "public": _PUBLIC, "protocol": PROTOCOL_VERSION,
                         "hub": os.environ.get("AIMARKET_HUB_URL", "https://modelmarket.dev")})


# A hosted endpoint gets called from browser-based MCP clients too, and the session header
# is invisible to them unless it is explicitly exposed. No credentials are involved: auth,
# when enabled at all, is a bearer header the caller supplies deliberately.
_middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST", "GET", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "mcp-session-id", "mcp-protocol-version"],
        expose_headers=["Mcp-Session-Id"],
        max_age=86400,
    )
]

app = Starlette(middleware=_middleware, routes=[
    Route("/health", health, methods=["GET"]),
    Route("/", handle_rpc, methods=["POST"]),
    Route("/", handle_get, methods=["GET"]),
    Route("/mcp", handle_rpc, methods=["POST"]),
    Route("/mcp", handle_get, methods=["GET"]),
    Route("/mcp", handle_delete, methods=["DELETE"]),
])


def main() -> None:
    import uvicorn
    port = int(os.environ.get("AIMARKET_MCP_PORT", "9090"))
    host = os.environ.get("AIMARKET_MCP_HOST", "0.0.0.0")
    # proxy_headers=False on purpose. Uvicorn's own handling rewrites request.client from
    # the LEFTMOST X-Forwarded-For entry, which is the one value a caller can put there
    # itself — every trial allowance and rate limit keyed on the client address would then
    # be forgeable with one header. _client_ip does the trusted-peer check instead.
    uvicorn.run(app, host=host, port=port, proxy_headers=False)


if __name__ == "__main__":
    main()

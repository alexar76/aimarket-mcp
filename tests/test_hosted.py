"""aimarket-mcp as a HOSTED endpoint — the guarantees a shared deployment must keep.

The stdio server is one process per human, so one trial identity per process is exactly
right. https://modelmarket.dev/mcp is one process for the whole internet, and every
property below is one that silently inverts when the process stops being private:

  * one identity per process  -> the third stranger ever to call the endpoint gets 402,
    and the "paste one URL" listing is dead on arrival;
  * client address from the socket peer -> behind nginx that is the proxy, so the whole
    internet shares one rate-limit bucket and one allowance;
  * trusting a forwarding header from anyone -> the allowance is farmable with one header.

These tests pin the inverted forms, so a future refactor cannot quietly restore them.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from aimarket_mcp import server, tools


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _client(peer: str = "127.0.0.1") -> httpx.AsyncClient:
    """An MCP client whose packets appear to arrive from `peer`."""
    transport = httpx.ASGITransport(app=server.app, client=(peer, 51234))
    return httpx.AsyncClient(transport=transport, base_url="http://t")


def _parse_sse(text: str) -> dict:
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise AssertionError(f"no data: frame in {text!r}")


async def _rpc(client, method, params=None, _id=1, headers=None):
    return await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": _id, "method": method, "params": params or {}},
        headers=headers or {},
    )


@pytest.fixture
def captured_visitors(monkeypatch):
    """Capture the trial identity each invoke actually presents to the hub."""
    seen: list = []

    async def fake_post(url, json=None, headers=None, **kwargs):  # noqa: A002 - mirrors safe_post
        seen.append((headers or {}).get("X-AIMarket-Sandbox-Visitor"))
        return _FakeResponse({"success": True, "result": {"ok": True}, "sandbox": True,
                              "receipt": {"nonce": "n-test"}})

    monkeypatch.setattr(tools, "safe_post", fake_post)
    return seen


async def _invoke(client, headers=None):
    return await _rpc(client, "tools/call", {
        "name": "market_invoke",
        "arguments": {"capability_id": "demo.cap@v1", "product_id": "prod-demo"},
    }, headers=headers)


# --- trial identity: the property that decides whether a hosted endpoint works at all ---

async def test_two_callers_get_two_identities(captured_visitors):
    async with _client("203.0.113.7") as a, _client("198.51.100.9") as b:
        await _invoke(a)
        await _invoke(b)
    assert len(captured_visitors) == 2
    assert captured_visitors[0] != captured_visitors[1], (
        "both callers presented one identity — a shared deployment would burn the whole "
        "trial allowance on whoever arrives first"
    )


async def test_same_caller_keeps_one_identity(captured_visitors):
    async with _client("203.0.113.7") as a:
        await _invoke(a)
        await _invoke(a)
    assert captured_visitors[0] == captured_visitors[1]


async def test_identity_never_carries_the_raw_client_address(captured_visitors):
    async with _client("203.0.113.7") as a:
        await _invoke(a, headers={"X-Real-IP": "203.0.113.7"})
    visitor = captured_visitors[0]
    assert "203.0.113.7" not in visitor
    assert visitor.startswith("mcpx-")
    assert 8 <= len(visitor) <= 64, "the hub refuses trial ids outside 8-64 chars"


async def test_identity_survives_concurrent_callers(captured_visitors, monkeypatch):
    """Two invokes in flight at once must not see each other's identity."""
    both_inside = asyncio.Event()
    arrivals = {"n": 0}
    observed: list = []

    async def fake_post(url, json=None, headers=None, **kwargs):  # noqa: A002
        arrivals["n"] += 1
        if arrivals["n"] >= 2:
            both_inside.set()
        await asyncio.wait_for(both_inside.wait(), timeout=5)
        # Read the context AFTER both requests are inside the handler: if the binding
        # leaked between tasks, these two reads would agree.
        observed.append(((headers or {}).get("X-AIMarket-Sandbox-Visitor"), tools.current_visitor()))
        return _FakeResponse({"success": True, "result": {}, "sandbox": True})

    monkeypatch.setattr(tools, "safe_post", fake_post)
    async with _client("203.0.113.7") as a, _client("198.51.100.9") as b:
        await asyncio.gather(_invoke(a), _invoke(b))

    assert len(observed) == 2
    for sent, in_context in observed:
        assert sent == in_context, "the identity changed under a concurrent request"
    assert observed[0][0] != observed[1][0]


def test_stdio_still_gets_one_identity_per_install():
    """Nothing bound = the stdio path, whose per-install identity must be untouched."""
    assert tools.current_visitor() == tools.SANDBOX_VISITOR


def test_binding_is_released_not_left_behind():
    token = tools.bind_visitor("mcpx-temporary")
    assert tools.current_visitor() == "mcpx-temporary"
    tools.release_visitor(token)
    assert tools.current_visitor() == tools.SANDBOX_VISITOR


# --- forwarding headers: only a peer we control may speak for someone else --------------

async def test_forwarding_header_from_an_untrusted_peer_is_ignored(captured_visitors):
    """A caller reaching the process directly cannot name itself something else."""
    async with _client("203.0.113.7") as direct:
        await _invoke(direct, headers={"X-Real-IP": "198.51.100.1"})
        await _invoke(direct, headers={"X-Forwarded-For": "198.51.100.2"})
        await _invoke(direct)
    assert captured_visitors[0] == captured_visitors[1] == captured_visitors[2], (
        "a forged forwarding header changed the trial identity — allowances become "
        "unlimited for anyone who can reach the process directly"
    )


async def test_forwarding_header_from_a_trusted_proxy_identifies_the_caller(captured_visitors):
    async with _client("127.0.0.1") as proxied:
        await _invoke(proxied, headers={"X-Real-IP": "198.51.100.1"})
        await _invoke(proxied, headers={"X-Real-IP": "198.51.100.2"})
    assert captured_visitors[0] != captured_visitors[1]


async def test_rightmost_forwarded_hop_wins_over_a_client_supplied_one(captured_visitors):
    """nginx appends the address it saw, so only the last hop is not caller-controlled."""
    async with _client("127.0.0.1") as proxied:
        await _invoke(proxied, headers={"X-Forwarded-For": "10.9.9.9, 198.51.100.5"})
        await _invoke(proxied, headers={"X-Forwarded-For": "203.0.113.1, 198.51.100.5"})
    assert captured_visitors[0] == captured_visitors[1], (
        "the leftmost X-Forwarded-For entry was used — that is the one a caller writes itself"
    )


async def test_a_forged_x_real_ip_cannot_outrank_the_forwarded_chain(captured_visitors):
    """X-Real-IP is a single-value header a caller can also send.

    nginx overwrites it, but other fronts pass it through, so reading it ahead of the
    append-only chain handed a fresh trial allowance to anyone who varied one header.
    """
    async with _client("127.0.0.1") as proxied:
        base = {"X-Forwarded-For": "198.51.100.5"}
        await _invoke(proxied, headers=base)
        await _invoke(proxied, headers={**base, "X-Real-IP": "1.1.1.1"})
        await _invoke(proxied, headers={**base, "X-Real-IP": "2.2.2.2"})
    assert len(set(captured_visitors)) == 1, (
        "one caller minted several identities by varying X-Real-IP"
    )


async def test_x_real_ip_is_still_used_when_there_is_no_forwarded_chain(captured_visitors):
    async with _client("127.0.0.1") as proxied:
        await _invoke(proxied, headers={"X-Real-IP": "198.51.100.7"})
        await _invoke(proxied, headers={"X-Real-IP": "198.51.100.8"})
    assert captured_visitors[0] != captured_visitors[1]


def test_only_loopback_is_trusted_by_default():
    """A private-range default would let any host on the same LAN, VPC or docker bridge
    name any caller it liked — and the allowance is keyed on that name."""
    assert server._peer_is_trusted("127.0.0.1")
    assert server._peer_is_trusted("::1")
    assert not server._peer_is_trusted("172.17.0.1")   # a container bridge must be declared
    assert not server._peer_is_trusted("10.1.2.3")
    assert not server._peer_is_trusted("8.8.8.8")
    assert not server._peer_is_trusted("not-an-address")


def test_a_declared_proxy_range_is_honoured():
    assert "172.17.0.1" in [str(n.network_address) for n in server._parse_trusted("172.17.0.1/32")]
    nets = server._parse_trusted("172.16.0.0/12,127.0.0.1/32")
    import ipaddress
    assert any(ipaddress.ip_address("172.17.0.1") in n for n in nets)


async def test_public_mode_does_not_let_a_bearer_header_mint_rate_buckets(monkeypatch):
    """_auth_ok never reads the header in public mode, so keying the limiter on it would
    hand a fresh bucket to anyone sending a new random token per request."""
    monkeypatch.setattr(server, "_API_KEY", "")
    monkeypatch.setattr(server, "_PUBLIC", True)
    monkeypatch.setattr(server, "_PRODUCTION", True)
    monkeypatch.setattr(server, "_RL_PER_MIN", 2)
    monkeypatch.setattr(server, "_buckets", {})
    async with _client("203.0.113.44") as c:
        codes = []
        for i in range(4):
            r = await _rpc(c, "ping", headers={"Authorization": f"Bearer tok-{i}"})
            codes.append(r.status_code)
    assert codes[-1] == 429, f"rotating the bearer bypassed the rate limit: {codes}"
    assert len(server._buckets) == 1, "one caller must not grow the bucket table per request"


# --- public mode: opt-in, never a default ------------------------------------------------

async def test_public_opt_in_lets_production_answer_anonymous_callers(monkeypatch):
    monkeypatch.setattr(server, "_API_KEY", "")
    monkeypatch.setattr(server, "_PRODUCTION", True)
    monkeypatch.setattr(server, "_PUBLIC", True)
    async with _client() as c:
        assert (await _rpc(c, "tools/list")).status_code == 200


async def test_public_mode_does_not_override_a_configured_key(monkeypatch):
    monkeypatch.setattr(server, "_API_KEY", "s3cret")
    monkeypatch.setattr(server, "_PUBLIC", True)
    async with _client() as c:
        assert (await _rpc(c, "tools/list")).status_code == 401
        ok = await _rpc(c, "tools/list", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200


async def test_health_reports_the_mode_a_canary_can_check(monkeypatch):
    monkeypatch.setattr(server, "_PUBLIC", True)
    async with _client() as c:
        body = (await c.get("/health")).json()
    assert body["status"] == "ok"
    assert body["public"] is True
    assert "market_invoke" in body["tools"]
    assert body["protocol"] == server.PROTOCOL_VERSION


# --- rate limiting: per caller, not per proxy --------------------------------------------

async def test_rate_limit_counts_callers_separately_behind_a_proxy(monkeypatch):
    monkeypatch.setattr(server, "_RL_PER_MIN", 2)
    monkeypatch.setattr(server, "_buckets", {})
    async with _client("127.0.0.1") as proxied:
        noisy = {"X-Real-IP": "198.51.100.20"}
        assert (await _rpc(proxied, "ping", headers=noisy)).status_code == 200
        assert (await _rpc(proxied, "ping", headers=noisy)).status_code == 200
        assert (await _rpc(proxied, "ping", headers=noisy)).status_code == 429
        # a different caller arriving through the same proxy is unaffected
        quiet = {"X-Real-IP": "198.51.100.21"}
        assert (await _rpc(proxied, "ping", headers=quiet)).status_code == 200


# --- transport manners a hosted endpoint needs for clients to connect at all -------------

async def test_get_is_refused_with_405_and_an_allow_header():
    """404 reads as 'wrong URL' to a client probing for a stream; 405 is the spec's answer."""
    async with _client() as c:
        r = await c.get("/mcp")
    assert r.status_code == 405
    assert "POST" in r.headers.get("allow", "")


async def test_session_delete_is_accepted():
    async with _client() as c:
        assert (await c.delete("/mcp")).status_code == 204


async def test_cors_preflight_exposes_the_session_header():
    async with _client() as c:
        r = await c.options("/mcp", headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,mcp-session-id",
        })
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"
    async with _client() as c:
        posted = await _rpc(c, "initialize", {"protocolVersion": server.PROTOCOL_VERSION},
                            headers={"Origin": "https://example.com"})
    assert "mcp-session-id" in posted.headers.get("access-control-expose-headers", "").lower()

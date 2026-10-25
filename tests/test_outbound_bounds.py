"""Network fixtures prove caps before buffering and preserve pinned HTTPS.

No sockets or external HTTP servers are used.
"""
from __future__ import annotations

import asyncio
import gzip
import socket
import zlib

import httpx
import pytest

from aimarket_mcp import security


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.read_count = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.read_count += 1
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])

    def install(handler):
        def client(**kwargs):
            assert kwargs["trust_env"] is False
            return original(transport=httpx.MockTransport(handler), **kwargs)
        monkeypatch.setattr(security.httpx, "AsyncClient", client)
    return install


@pytest.mark.parametrize("method", [security.safe_get, security.safe_post])
async def test_excess_body_is_closed_before_later_chunks_are_read(transport, method):
    stream = Chunks([b"a" * 16_384, b"b" * 16_384, b"must-not-be-read"])
    transport(lambda request: httpx.Response(200, stream=stream, headers={"content-length": "1"}))
    with pytest.raises(ValueError, match="exceeds"):
        await method("https://peer.example/result", max_bytes=20_000)
    assert stream.closed
    assert stream.read_count == 2


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
@pytest.mark.parametrize("method", [security.safe_get, security.safe_post])
async def test_cap_counts_decompressed_bytes(transport, method, encoding, compress):
    stream = Chunks([compress(b"x" * 100_000)])
    transport(lambda request: httpx.Response(200, stream=stream, headers={"content-encoding": encoding}))
    with pytest.raises(ValueError, match="decoded bytes"):
        await method("https://peer.example/result", max_bytes=4096)
    assert stream.closed


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
async def test_valid_compressed_result_is_readable_and_preserves_https_identity(transport, encoding, compress):
    seen = []

    def upstream(request):
        seen.append(request)
        return httpx.Response(200, stream=Chunks([compress(b"hello")]), headers={
            "content-encoding": encoding, "content-type": "text/plain; charset=utf-8",
        })

    transport(upstream)
    response = await security.safe_get("https://peer.example:8443/result", max_bytes=5)
    assert response.text == "hello"
    assert response.headers.get("content-encoding") is None
    assert response.headers["content-length"] == "5"
    assert str(seen[0].url) == "https://93.184.216.34:8443/result"
    assert seen[0].headers["host"] == "peer.example:8443"
    assert seen[0].extensions["sni_hostname"] == "peer.example"


async def test_redirect_revalidates_destination_without_reading_its_body(transport, monkeypatch):
    stream = Chunks([b"not needed"])
    seen = []

    def upstream(request):
        seen.append(request)
        return httpx.Response(302, stream=stream, headers={"location": "http://127.0.0.1/private"})

    transport(upstream)
    with pytest.raises(ValueError, match="private"):
        await security.safe_get("https://peer.example/result")
    assert len(seen) == 1
    assert stream.closed and stream.read_count == 0


@pytest.mark.parametrize("method", [security.safe_get, security.safe_post])
async def test_deadline_closes_a_slow_stream(transport, method):
    stream = Chunks([b"later"], delay=1)
    transport(lambda request: httpx.Response(200, stream=stream))
    with pytest.raises(httpx.TimeoutException, match="deadline"):
        await method("https://peer.example/result", timeout=0.05)
    assert stream.closed


async def test_concurrent_requests_share_a_bounded_admission_budget(transport):
    release = asyncio.Event()
    ready = asyncio.Event()
    active = peak = 0

    async def upstream(request):
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        if active == 8:
            ready.set()
        await release.wait()
        active -= 1
        return httpx.Response(200, stream=Chunks([b"ok"]))

    transport(upstream)
    requests = [asyncio.create_task(security.safe_post("https://peer.example/result")) for _ in range(12)]
    try:
        await asyncio.wait_for(ready.wait(), timeout=2)
        assert active == 8
    finally:
        release.set()
        results = await asyncio.gather(*requests)
    assert peak == 8
    assert all(result.content == b"ok" for result in results)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
async def test_unbounded_or_invalid_deadlines_are_refused(timeout):
    with pytest.raises(ValueError, match="timeout"):
        await security.safe_get("https://peer.example/result", timeout=timeout)

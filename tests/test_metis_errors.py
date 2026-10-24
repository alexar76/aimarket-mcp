"""Metis failures remain MCP errors with useful, credential-free diagnostics."""
import json

import httpx
import pytest

from aimarket_mcp import tools


@pytest.mark.parametrize("failure,reason,status", [
    ("timeout", "timeout", None),
    ("connection", "connection", None),
    ("http", "http_status", 503),
    ("non_json", "invalid_response", 200),
    ("array", "invalid_response", 200),
    ("blocked", "invalid_endpoint", None),
])
async def test_metis_failures_redact_credentials(monkeypatch, failure, reason, status):
    monkeypatch.setattr(tools, "METIS_URL", "https://user:password@metis.example:8443/base?key=query-secret")
    monkeypatch.setattr(tools, "METIS_KEY", "bearer-secret")

    async def fake_post(url, **kwargs):
        request = httpx.Request("POST", url, headers=kwargs["headers"])
        if failure == "timeout":
            raise httpx.ReadTimeout("bearer-secret query-secret", request=request)
        if failure == "connection":
            raise httpx.ConnectError("password query-secret", request=request)
        if failure == "blocked":
            raise ValueError("password query-secret")
        if failure == "http":
            return httpx.Response(503, text="bearer-secret", request=request)
        if failure == "array":
            return httpx.Response(200, json=["bearer-secret"], request=request)
        return httpx.Response(200, text="<html>bearer-secret</html>", request=request)

    monkeypatch.setattr(tools, "safe_post", fake_post)
    with pytest.raises(ValueError) as caught:
        await tools.metis_verify({"input": "Question with private context"})
    message = str(caught.value)
    data = json.loads(message)
    assert data["error"] == "metis_verify_failed"
    assert data["reason"] == reason
    assert data["status_code"] == status
    assert data["url"] == "https://metis.example:8443/base"
    assert "AIMARKET_METIS_URL" in data["hint"]
    for secret in ("user:", "password", "query-secret", "bearer-secret", "private context"):
        assert secret not in message


async def test_metis_success_keeps_answer_and_verification(monkeypatch):
    async def fake_post(url, **kwargs):
        return httpx.Response(200, json={
            "answer": "4", "verify_score": 0.9, "verified": True,
            "status": "ok", "route": "fast",
        }, request=httpx.Request("POST", url))
    monkeypatch.setattr(tools, "safe_post", fake_post)
    result = await tools.metis_verify({"input": "2+2", "route": "fast"})
    assert result.startswith("4\n")
    assert "verify_score=0.9" in result
    assert "verified=True" in result


async def test_metis_failure_is_a_protocol_tool_error(monkeypatch):
    from aimarket_mcp import server

    monkeypatch.setattr(server, "_API_KEY", "")
    monkeypatch.setattr(server, "_PRODUCTION", False)

    async def fake_post(url, **kwargs):
        raise httpx.ConnectError("internal transport detail")

    monkeypatch.setattr(tools, "safe_post", fake_post)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1:9090",
    ) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "metis_verify", "arguments": {"input": "2+2"}},
        })
    frame = next(line[5:] for line in response.text.splitlines() if line.startswith("data:"))
    result = json.loads(frame)["result"]
    assert result["isError"] is True
    assert "metis_verify_failed" in result["content"][0]["text"]
    assert "internal transport detail" not in result["content"][0]["text"]

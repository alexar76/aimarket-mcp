"""AIMARKET_API_KEY: a key from the hub's /start page pays where the free trial stops.

The stdio install is what /developers offers as the second door (`pip install aimarket-mcp`),
and it used to end at the trial with "paid access needs an on-chain escrow deposit, an
operator action". Now a key in the server's environment pays from a prepaid balance; a short
balance still gets the trial, an unknown key is refused (never a silent free call), and the
wall names the key first.
"""
from __future__ import annotations

import json

import pytest

from aimarket_mcp import tools

ARGS = {"capability_id": "gaia.weather.read@v1", "product_id": "gaia.gateway",
        "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}}


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._body


@pytest.fixture
def hub(monkeypatch):
    """The hub, answering from a script; records the headers of every call."""
    state = {"calls": [], "replies": []}

    async def fake_post(url, json=None, headers=None, **kwargs):  # noqa: A002
        state["calls"].append(dict(headers or {}))
        status, body = state["replies"].pop(0)
        return _Resp(status, body)

    monkeypatch.setattr(tools, "safe_post", fake_post)
    monkeypatch.setattr(tools, "HUB_URL", "https://hub.example")
    return state


async def test_a_key_pays_from_the_balance(hub, monkeypatch):
    monkeypatch.setattr(tools, "API_KEY", "aimk_" + "K" * 32)
    hub["replies"] = [(200, {"success": True, "output": {"t": 14}, "price_usd": 0.001,
                             "receipt": {"nonce": "n1"}})]
    text = await tools.market_invoke(ARGS)
    assert len(hub["calls"]) == 1
    assert hub["calls"][0]["X-API-Key"] == "aimk_" + "K" * 32
    assert "X-AIMarket-Sandbox-Visitor" not in hub["calls"][0], "a sandbox call would be free"
    assert '"charged_usd": 0.001' in text


async def test_a_short_balance_falls_back_to_the_trial(hub, monkeypatch):
    monkeypatch.setattr(tools, "API_KEY", "aimk_" + "K" * 32)
    hub["replies"] = [(402, {"error": "payment_required", "needed": 0.001, "balance": 0.0}),
                      (200, {"success": True, "output": {"t": 14}, "sandbox": True})]
    text = await tools.market_invoke(ARGS)
    keyed, trial = hub["calls"]
    assert "X-API-Key" in keyed and "X-API-Key" not in trial
    assert trial.get("X-AIMarket-Sandbox-Visitor")
    assert '"sandbox": true' in text


async def test_short_balance_and_spent_trial_point_at_the_top_up(hub, monkeypatch):
    monkeypatch.setattr(tools, "API_KEY", "aimk_" + "K" * 32)
    hub["replies"] = [(402, {"error": "payment_required", "needed": 0.001, "balance": 0.0021}),
                      (429, {"error": "trial_quota_exhausted"})]
    text = await tools.market_invoke(ARGS)
    assert "$0.0021" in text and "https://hub.example/start#topup" in text


async def test_an_unknown_key_is_refused_not_served_free(hub, monkeypatch):
    monkeypatch.setattr(tools, "API_KEY", "aimk_typo")
    hub["replies"] = [(401, {"error": "invalid_api_key"})]
    text = await tools.market_invoke(ARGS)
    assert len(hub["calls"]) == 1, "no silent fall back to the trial"
    assert "AIMARKET_API_KEY is not a key" in text and "https://hub.example/start" in text


async def test_without_a_key_the_wall_offers_one(hub, monkeypatch):
    monkeypatch.setattr(tools, "API_KEY", "")
    hub["replies"] = [(429, {"error": "trial_quota_exhausted"})]
    text = await tools.market_invoke(ARGS)
    assert "https://hub.example/start" in text and "AIMARKET_API_KEY" in text
    assert "X-API-Key" not in hub["calls"][0]


async def test_a_listing_credits_cannot_buy_is_named(hub, monkeypatch):
    monkeypatch.setattr(tools, "API_KEY", "aimk_" + "K" * 32)
    hub["replies"] = [(402, {"error": "payment_required", "detail":
                             "this listing pays its seller directly, so it cannot be bought with hub credits"}),
                      (429, {"error": "trial_quota_exhausted"})]
    assert "cannot buy it" in await tools.market_invoke(ARGS)

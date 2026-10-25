"""A URL that passed the SSRF check must be the URL that gets connected to.

`validate_url` resolved the hostname and rejected private/loopback/link-local answers — and
then the request was made against the HOSTNAME, so httpx resolved it again at connect time.
Nothing carried the address that passed the check, which is a plain time-of-check /
time-of-use gap: a name that answers public once and private a moment later goes straight
through. That is DNS rebinding, i.e. the ordinary way this check is defeated.
"""

from __future__ import annotations

import socket

import pytest

from aimarket_mcp import security


def test_a_hostname_is_pinned_to_the_address_that_was_validated(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    target, headers, _ = security.pin_target("http://peer.example/path?q=1")
    assert target == "http://93.184.216.34/path?q=1", target
    assert headers.get("Host") == "peer.example", "the origin's Host header must survive"


def test_the_rebind_that_used_to_work_no_longer_does(monkeypatch):
    """First answer public (the check), second answer loopback (the connect)."""
    answers = [
        [(2, 1, 6, "", ("93.184.216.34", 0))],
        [(2, 1, 6, "", ("127.0.0.1", 0))],
    ]

    def flipping(*_a, **_k):
        return answers.pop(0) if answers else [(2, 1, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", flipping)
    security.validate_url("http://rebind.example/x")      # passes, as before

    # Two safe outcomes, and the old code produced neither: either the second lookup is
    # caught and the request is REFUSED, or it is pinned to a public address. What must not
    # happen is a connection to the rebound address, which is what handing the hostname to
    # httpx did.
    try:
        target, _, _ = security.pin_target("http://rebind.example/x")
    except ValueError:
        return                                            # refused — the safe outcome
    assert "127.0.0.1" not in target, f"the connect target followed the rebind: {target}"


def test_a_private_answer_is_refused_by_the_pinner_too(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0))]
    )
    with pytest.raises(ValueError):
        security.pin_target("http://internal.example/x")


def test_a_name_answering_both_public_and_private_is_refused(monkeypatch):
    """One good answer does not make the name safe — the next lookup picks again."""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [
            (2, 1, 6, "", ("93.184.216.34", 0)),
            (2, 1, 6, "", ("169.254.169.254", 0)),
        ],
    )
    with pytest.raises(ValueError):
        security.pin_target("http://mixed.example/x")


def test_https_is_pinned_too_with_the_name_in_sni(monkeypatch):
    """HTTPS used to keep its hostname, so a rebinding name went wherever its second answer
    pointed. The sni_hostname extension keeps the handshake and the certificate check on the
    name while the connection goes to the address that passed."""
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))]
    )
    target, headers, extensions = security.pin_target("https://peer.example:8443/x")
    assert target == "https://93.184.216.34:8443/x"
    assert headers == {"Host": "peer.example:8443"}
    assert extensions == {"sni_hostname": "peer.example"}


@pytest.mark.parametrize("address", [
    "64:ff9b::7f00:1",   # NAT64 form of 127.0.0.1, which Python calls global
    "64:ff9b::a00:5",    # NAT64 form of 10.0.0.5
    "2002:a9fe:a9fe::",  # 6to4 form of 169.254.169.254
    "::ffff:10.0.0.5",
])
def test_an_ipv6_address_carrying_a_private_ipv4_is_refused(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(10, 1, 6, "", (address, 0, 0, 0))]
    )
    with pytest.raises(ValueError):
        security.pin_target("https://wrapped.example/x")
    with pytest.raises(ValueError):
        security.validate_url("https://wrapped.example/x")


def test_an_ip_literal_needs_no_pinning(monkeypatch):
    target, headers, extensions = security.pin_target("http://93.184.216.34:8080/x")
    assert target == "http://93.184.216.34:8080/x" and headers == {} and extensions == {}


def test_safe_get_and_safe_post_both_pin():
    import inspect

    for fn in (security.safe_get, security.safe_post):
        src = inspect.getsource(fn)
        assert "pin_target" in src, f"{fn.__name__} still connects by hostname"

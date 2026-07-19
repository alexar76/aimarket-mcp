"""Security core for the ecosystem MCP gateway — vendored from metis's audited helpers so
the server has zero coupling but the same hardening: SSRF-safe outbound HTTP (scheme
allow-list, private-IP block, per-redirect re-validation) and untrusted-output sanitization.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
from typing import Optional, Set
from urllib.parse import urlparse

import httpx

_BLOCKED_HOSTS = frozenset({
    "localhost", "localhost.localdomain",
    "metadata.google.internal", "metadata.goog",
})
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_REDIRECTS = 3
_MAX_TOOL_OUTPUT = 50_000


def _is_private_ip(hostname: str) -> bool:
    try:
        addr = ipaddress.ip_address(hostname)
        return (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast)
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_reserved or addr.is_multicast):
                return True
    except (socket.gaierror, OSError):
        return True   # fail closed on resolution failure
    return False


def validate_url(url: str, *, allowed_schemes: Optional[Set[str]] = None) -> str:
    schemes = allowed_schemes or _ALLOWED_SCHEMES
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    host = parsed.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"Hostname '{host}' is not allowed")
    if _is_private_ip(host):
        raise ValueError(f"Hostname '{host}' resolves to a private/reserved address")
    return url.strip()


async def safe_get(url: str, *, timeout: float = 15.0, max_redirects: int = _MAX_REDIRECTS,
                   headers: Optional[dict] = None, max_bytes: int = 2_000_000) -> httpx.Response:
    """GET with SSRF re-validation on every redirect hop and a response-size cap."""
    validate_url(url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers or {}) as client:
        current = url
        for _ in range(max_redirects + 1):
            validate_url(current)
            resp = await client.get(current)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    return resp
                current = str(resp.url.join(loc))
                continue
            if len(resp.content) > max_bytes:
                raise ValueError(f"Response exceeds {max_bytes} bytes")
            return resp
        raise ValueError(f"Too many redirects (max {max_redirects})")


async def safe_post(url: str, *, data=None, json=None, timeout: float = 30.0,
                    headers: Optional[dict] = None) -> httpx.Response:
    validate_url(url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers or {}) as client:
        return await client.post(url, data=data, json=json)


_ROLE_MARKER = re.compile(r"\[\s*(system|assistant|user|human|ai)\s*\]\s*", re.I)


def sanitize_tool_output(output: str, *, max_length: int = _MAX_TOOL_OUTPUT) -> str:
    """Neutralize untrusted tool/web output before it reaches the model: strip forged role
    markers (fixpoint), cap length, and wrap in an <untrusted> boundary."""
    text = output or ""
    if len(text) > max_length:
        text = text[:max_length] + "\n…[truncated]"
    for _ in range(8):                       # fixpoint — nested markers can't reconstruct
        stripped = _ROLE_MARKER.sub("", text)
        if stripped == text:
            break
        text = stripped
    return f"<untrusted>\n{text}\n</untrusted>"


_TAG = re.compile(r"<(script|style|noscript|template|svg)\b.*?</\1>", re.I | re.S)
_BLOCK = re.compile(r"</(p|div|li|h[1-6]|tr|section|article|br)>", re.I)
_ANYTAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n\s*\n\s*\n+")


def extract_main_text(html_text: str, *, max_chars: int = 20_000) -> str:
    """Dependency-free readability-lite: drop scripts/styles, keep block structure, unescape
    entities, collapse whitespace. Good enough to feed a model; never executes anything."""
    body = html_text
    m = re.search(r"<body\b[^>]*>(.*)</body>", body, re.I | re.S)
    if m:
        body = m.group(1)
    body = _TAG.sub(" ", body)
    body = _BLOCK.sub("\n", body)
    body = _ANYTAG.sub("", body)
    body = html.unescape(body)
    body = _WS.sub(" ", body)
    body = _NL.sub("\n\n", body)
    body = "\n".join(line.strip() for line in body.splitlines())
    body = body.strip()
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…[truncated]"
    return body

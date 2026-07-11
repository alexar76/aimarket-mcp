<!-- aicom-mirror-notice -->
> **📖 Read-only mirror.** `aimarket-mcp` is published from the canonical AI-Factory monorepo.
> **Pull requests are not accepted** — any commit pushed here is overwritten by
> `scripts/mirror_satellites.sh` on the next sync.
> 🐞 Found a bug or have a request? Please **[open an issue](https://github.com/alexar76/aimarket-mcp/issues)**.

<!-- aicom-readme-badges -->
<p align="center">
  <a href="https://github.com/alexar76/aimarket-mcp/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/alexar76/aimarket-mcp/ci.yml?branch=main&label=CI" alt="CI" /></a>
  <img src="https://img.shields.io/badge/MCP-gateway-6e40c9" alt="MCP gateway" />
  <img src="https://img.shields.io/badge/tests-12_passing-brightgreen" alt="12 tests passing" />
  <a href="docs/badges/coverage.svg"><img src="docs/badges/coverage.svg" alt="Test coverage" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" /></a>
</p>
<!-- /aicom-readme-badges -->

# aimarket-mcp — ecosystem MCP gateway

The alexar76 AICOM / AIMarket ecosystem's shared **MCP gateway**: one hardened server that
gives every agent (Metis, ARGUS, …) the generic capabilities they were missing — **web
fetch**, **web search**, and **Metis verification** — behind a single MCP endpoint.

It speaks **MCP over Streamable-HTTP** (JSON-RPC 2.0 POST, SSE-`data:`-framed responses,
`Mcp-Session-Id`) — the exact protocol Metis's MCP client and ARGUS already talk, so no
external SDK is required.

## Tools

| Tool | What it does | Hardening |
|------|--------------|-----------|
| `web_fetch` | Fetch a URL, return its main text (readability-lite) | SSRF-guarded (scheme allow-list, private-IP block, per-redirect re-validation, size cap); output sanitized + `<untrusted>`-wrapped |
| `web_search` | Live DuckDuckGo search → top snippets | output sanitized |
| `metis_verify` | Run Metis's cognition + verification envelope on an input | returns answer + machine-readable `verify_score`/`verified` |

Why a gateway (not per-agent tools): generic capabilities are written **once** and every
ecosystem agent gets them; the security core lives in one audited place. Ecosystem-specific
capabilities already live in their own MCP servers (`aimarket-oracle-gateway`,
`aimarket-plugins`); MNEMOSYNE-search and on-chain tools are the next additions here.

## Security

- **SSRF**: `web_fetch` validates the scheme (http/https only), blocks localhost/private/
  reserved IPs, and re-validates on every redirect hop (vendored from Metis's audited
  `security/ssrf.py`).
- **Untrusted output**: every web result is length-capped, has forged role markers stripped
  to a fixpoint, and is wrapped in `<untrusted>…</untrusted>` before it can reach a model.
- **Auth**: optional bearer (`AIMARKET_MCP_KEY`); **fail-closed** in production
  (`AIMARKET_MCP_PRODUCTION=1` requires a key).
- **Rate limit**: per-key/IP token bucket (`AIMARKET_MCP_RATE`, default 120/min).

## Run

```bash
pip install -e .
AIMARKET_MCP_KEY=sk-... AIMARKET_MCP_PRODUCTION=1 aimarket-mcp   # :9090
# or: docker compose up -d
```

Env: `AIMARKET_MCP_PORT` (9090) · `AIMARKET_MCP_KEY` · `AIMARKET_MCP_PRODUCTION` ·
`AIMARKET_MCP_RATE` · `AIMARKET_METIS_URL` (for `metis_verify`) · `AIMARKET_METIS_KEY` ·
`AIMARKET_SEARCH_URL`.

## Consumers

- **Metis** — enable the preset:
  ```yaml
  enable_mcp_tools: true
  mcp_ecosystem_presets: [aimarket-web]
  ```
- **ARGUS** — add the server to `argus.config.json` `mcpServers` (see that repo).

## Test

```bash
pip install -e '.[dev]' && pytest -q
```

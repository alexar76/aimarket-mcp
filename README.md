<!-- aicom-mirror-notice -->
> **🔄 Synced from a monorepo — but with a live history.** `aimarket-mcp` mirrors the
> canonical AI-Factory monorepo. History here is append-only (no force-push).
> **Pull requests are welcome** — merged PRs are imported back into the monorepo
> and re-synced here, so your contribution becomes canonical.
> 💬 **[Issues](https://github.com/alexar76/aimarket-mcp/issues)** · **[Pull requests](https://github.com/alexar76/aimarket-mcp/pulls)** both welcome.

# aimarket-mcp — ecosystem MCP gateway

<!-- mcp-name: io.github.alexar76/aimarket-mcp -->

<!-- aicom-readme-badges -->
<p align="center">
  <a href="https://github.com/alexar76/aimarket-mcp/actions/workflows/ci.yml"><img src="https://github.com/alexar76/aimarket-mcp/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://glama.ai/mcp/servers/alexar76/aimarket-mcp"><img src="https://glama.ai/mcp/servers/alexar76/aimarket-mcp/badges/score.svg" alt="aimarket-mcp MCP server" /></a>
  <img src="https://raw.githubusercontent.com/alexar76/aimarket-mcp/refs/heads/main/docs/badges/mcp.svg" alt="MCP gateway" />
  <img src="https://raw.githubusercontent.com/alexar76/aimarket-mcp/refs/heads/main/docs/badges/transport.svg" alt="stdio + HTTP" />
  <img src="https://raw.githubusercontent.com/alexar76/aimarket-mcp/refs/heads/main/docs/badges/tests.svg" alt="14 tests passing" />
  <a href="https://raw.githubusercontent.com/alexar76/aimarket-mcp/refs/heads/main/docs/badges/coverage.svg"><img src="https://raw.githubusercontent.com/alexar76/aimarket-mcp/refs/heads/main/docs/badges/coverage.svg" alt="Test coverage" /></a>
  <a href="https://github.com/alexar76/aimarket-mcp/blob/main/LICENSE"><img src="https://raw.githubusercontent.com/alexar76/aimarket-mcp/refs/heads/main/docs/badges/license.svg" alt="License: MIT" /></a>
</p>
<!-- /aicom-readme-badges -->

> 🌐 **English** · [Русский](https://github.com/alexar76/aimarket-mcp/blob/main/docs/README.ru.md) · [Español](https://github.com/alexar76/aimarket-mcp/blob/main/docs/README.es.md) · [Français](https://github.com/alexar76/aimarket-mcp/blob/main/docs/README.fr.md) · [中文](https://github.com/alexar76/aimarket-mcp/blob/main/docs/README.zh.md) · [Glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)




> ### 🟢 Just want to try the marketplace? Install nothing.
> Paste **`https://modelmarket.dev/mcp`** into your MCP client and you have `market_search`
> and `market_invoke` against the live hub, with a few free trial invokes per caller and a
> signed receipt for each — no wallet, no key, no install.
> → [`docs/hosted-mcp-endpoint.md`](https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md)
>
> Install **this** package when you want the other three tools (`web_fetch`, `web_search`,
> `metis_verify`), or want to point the market tools at a hub of your own.

**One MCP gateway. Five hardened tools. Shared by Metis, ARGUS, and the ecosystem.**

Transport: **stdio** (`aimarket_mcp/stdio_server.py`) for Glama / Claude Desktop / Cursor, built with the
official **Model Context Protocol** Python SDK ([`mcp`](https://github.com/modelcontextprotocol/python-sdk), `FastMCP`).
Also ships **Streamable-HTTP** on `:9090` for self-hosted deployments (`aimarket-mcp-http`, Docker Compose).

| Item | Location |
|------|----------|
| MCP entrypoint (stdio) | `aimarket_mcp/stdio_server.py` |
| MCP gateway (HTTP) | [`aimarket_mcp/server.py`](aimarket_mcp/server.py) |
| Tool handlers + security | [`aimarket_mcp/tools.py`](aimarket_mcp/tools.py), [`aimarket_mcp/security.py`](aimarket_mcp/security.py) |
| Glama / Docker (stdio) | [`Dockerfile`](Dockerfile), [`glama.json`](glama.json) |
| Self-host HTTP | [`Dockerfile.http`](Dockerfile.http), [`docker-compose.yml`](docker-compose.yml) |

Compatible hosts: Claude Desktop, Cursor, Glama, and any MCP client that supports stdio or Streamable-HTTP.

## Tools

| Tool | What it does | Hardening |
|------|--------------|-----------|
| `web_fetch` | Fetch a URL, return main text (readability-lite) | SSRF-guarded; output sanitized + `<untrusted>`-wrapped |
| `web_search` | Live DuckDuckGo search → top snippets | output sanitized + `<untrusted>` |
| `metis_verify` | Metis cognition + verification envelope | returns answer + `verify_score` / `verified` gate |
| `market_search` | Discover priced capabilities on an AIMarket hub | free; no wallet, key or channel; the hub lists only what it can execute |
| `market_invoke` | Run one on the hub's free trial tier | returns the signed receipt nonce; reports the hub's 402 verbatim when the allowance is spent |
| `market_status` | Show the free trial invokes and prepaid balance left | read-only; the hub's health, this installation's remaining trial in the current window, and the `AIMARKET_API_KEY` balance when set (never the key) |

### Example — buy a GAIA Open-Meteo reading

```text
market_search_tool(intent="gaia weather open-meteo")
market_invoke_tool(
  capability_id="gaia.weather.read@v1",
  product_id="gaia.gateway",
  source_hub="https://iot.modelmarket.dev",
  # input JSON with device_id om-wx-01 — see tool schema / hub docs
)
```

Or the same HTTP the tool wraps:

```bash
curl -s -X POST "${AIMARKET_HUB_URL:-https://modelmarket.dev}/ai-market/v2/invoke" \
  -H 'Content-Type: application/json' \
  -H 'X-AIMarket-Sandbox-Visitor: vis_mcp_om_wx' \
  -d '{"capability_id":"gaia.weather.read@v1","product_id":"gaia.gateway",
       "source_hub":"https://iot.modelmarket.dev","input":{"device_id":"om-wx-01"}}'
```

That is the **easy** path (trial/sandbox). Proving an **external wallet** paid on-chain
is a separate escrow flow (`openChannel` → DebitAuthorization → hub debit/settle) —
see [`docs/onchain-journal.md`](https://github.com/alexar76/aicom/blob/main/docs/onchain-journal.md) §3l–§3m and
[`gaia/docs/LIVE-RELAYS.md`](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md).

Why a gateway (not per-agent tools): generic capabilities are written **once**; the security core lives in one audited place. Ecosystem-specific capabilities live in their own MCP servers (`aimarket-oracle-gateway`, `aimarket-plugins`).

## Configure (env)

| var | meaning |
|-----|---------|
| `AIMARKET_METIS_URL` | Metis verify API base (default `https://metis.modelmarket.dev`) |
| `AIMARKET_METIS_KEY` | optional bearer for Metis verify |
| `AIMARKET_SEARCH_URL` | DuckDuckGo HTML endpoint override |
| `AIMARKET_HUB_URL` | AIMarket hub for `market_search` / `market_invoke` (default `https://modelmarket.dev`) |
| `AIMARKET_API_KEY` | Credit-account key from the hub's `/start` page (`https://modelmarket.dev/start`): priced `market_invoke` calls are paid from its prepaid balance; while it is short the free trial still applies. In HTTP mode it pays for every caller of that server |
| `AIMARKET_SANDBOX_VISITOR` | Trial identity for `market_invoke`; random per install, set it to keep an allowance across reinstalls |
| `AIMARKET_MCP_KEY` | HTTP only — bearer auth key. Without one the server answers only this machine's user: a loopback packet with a loopback `Host`, no forwarding headers, no cross-site browser `Origin`, and on Linux a socket owned by the user the server runs as. That last check is what refuses a reverse proxy on the same machine whose workers run as their own user: nginx's default `proxy_pass` sends a loopback `Host` and no forwarding header. **Behind any reverse proxy, set a key** anyway: a proxy running as the server's own user, or any proxy on macOS or Windows, still looks local. In the HTTP Docker image (callers arrive from the bridge) every keyless call gets 401: set a key or `AIMARKET_MCP_PUBLIC=1` |
| `AIMARKET_MCP_PUBLIC` | HTTP only — `1` answers anonymous callers from anywhere, without a key (an explicit choice for a public endpoint) |
| `AIMARKET_MCP_HOST` | HTTP only — listen address (default `127.0.0.1`; the HTTP image sets `0.0.0.0`) |
| `AIMARKET_MCP_PRODUCTION` | HTTP only — `1` requires `AIMARKET_MCP_KEY` (fail-closed) |
| `AIMARKET_MCP_RATE` | HTTP only — requests/min per key/IP (default 120) |
| `AIMARKET_MCP_PORT` | HTTP only — listen port (default 9090) |

## Run (stdio — Glama / Claude Desktop)

Claude Desktop (`mcpServers` entry) — no clone, no working directory to get wrong:

```json
{
  "mcpServers": {
    "aimarket-mcp": {
      "command": "uvx",
      "args": ["aimarket-mcp"]
    }
  }
}
```

`uvx` fetches the published package and runs its `aimarket-mcp` console script, which is
the stdio server. With the package already installed, `"command": "aimarket-mcp"` and no
args does the same thing.

From a checkout, for development:

```bash
pip install -e .
python -m aimarket_mcp.stdio_server
```

## Run (HTTP — self-host)

```bash
pip install -e .
AIMARKET_MCP_KEY=sk-... AIMARKET_MCP_PRODUCTION=1 aimarket-mcp-http   # :9090
# or: docker compose up -d   (uses Dockerfile.http)
```

### Cursor / Claude (Streamable HTTP)

```json
{
  "mcpServers": {
    "aimarket-web": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:9090/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_AIMARKET_MCP_KEY"
      }
    }
  }
}
```

## Publish on Glama

Listing: [aimarket-mcp](https://glama.ai/mcp/servers/alexar76/aimarket-mcp).
Glama generates a container from the build settings in its admin panel:

| Field | Value |
|-------|-------|
| Build steps | `["bash scripts/glama_install.sh"]` |
| CMD arguments | `["mcp-proxy", "--", ".venv/bin/python", "-m", "aimarket_mcp.stdio_server"]` |
| Placeholder parameters | `{}` |
| Pinned commit SHA | empty (latest synced commit) |

Build, inspect, and publish a release after syncing source changes. A repository
sync alone does not refresh the deployed tool catalog or its quality evaluation.
The catalog should contain all six tools listed above.
See [Glama build and release instructions](https://github.com/alexar76/aimarket-mcp/blob/main/docs/GLAMA.md).

## Consumers

- Connected successfully? Share your host, configuration, and one working tool using
  the [Show and tell template](https://github.com/alexar76/aimarket-mcp/blob/main/docs/show-and-tell-template.md).
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

## Registries

See the [directory submission checklist and current status](https://github.com/alexar76/aimarket-mcp/blob/main/docs/REGISTRIES.md)
before submitting or refreshing a listing.

| Registry | Listing |
|----------|---------|
| **Glama** | [glama.ai/mcp/servers/alexar76/aimarket-mcp](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) |
| **Official MCP Registry** | `io.github.alexar76/aimarket-mcp` — `server.json` + GitHub Actions |
| **PyPI** | `pip install aimarket-mcp` |
| **GitHub Releases** | [github.com/alexar76/aimarket-mcp/releases](https://github.com/alexar76/aimarket-mcp/releases) |

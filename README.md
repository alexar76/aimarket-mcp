<!-- aicom-mirror-notice -->
> **📖 Read-only mirror.** `aimarket-mcp` is published from the canonical AI-Factory monorepo.
> **Pull requests are not accepted** — any commit pushed here is overwritten by
> `scripts/mirror_satellites.sh` on the next sync.
> 🐞 Found a bug or have a request? Please **[open an issue](https://github.com/alexar76/aimarket-mcp/issues)**.

# aimarket-mcp — ecosystem MCP gateway

<!-- mcp-name: io.github.alexar76/aimarket-mcp -->

<!-- aicom-readme-badges -->
<p align="center">
  <a href="https://github.com/alexar76/aimarket-mcp/actions/workflows/ci.yml"><img src="docs/badges/ci.svg" alt="CI" /></a>
  <a href="https://glama.ai/mcp/servers/alexar76/aimarket-mcp"><img src="https://glama.ai/mcp/servers/alexar76/aimarket-mcp/badges/score.svg" alt="aimarket-mcp MCP server" /></a>
  <img src="docs/badges/mcp.svg" alt="MCP gateway" />
  <img src="docs/badges/transport.svg" alt="stdio + HTTP" />
  <img src="docs/badges/tests.svg" alt="14 tests passing" />
  <a href="docs/badges/coverage.svg"><img src="docs/badges/coverage.svg" alt="Test coverage" /></a>
  <a href="LICENSE"><img src="docs/badges/license.svg" alt="License: MIT" /></a>
</p>
<!-- /aicom-readme-badges -->




**One MCP gateway. Three hardened tools. Shared by Metis, ARGUS, and the ecosystem.**

Transport: **stdio** (`mcp_stdio_server.py`) for Glama / Claude Desktop / Cursor, built with the
official **Model Context Protocol** Python SDK ([`mcp`](https://github.com/modelcontextprotocol/python-sdk), `FastMCP`).
Also ships **Streamable-HTTP** on `:9090` for self-hosted deployments (`aimarket-mcp-http`, Docker Compose).

| Item | Location |
|------|----------|
| MCP entrypoint (stdio) | [`mcp_stdio_server.py`](mcp_stdio_server.py) |
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

Why a gateway (not per-agent tools): generic capabilities are written **once**; the security core lives in one audited place. Ecosystem-specific capabilities live in their own MCP servers (`aimarket-oracle-gateway`, `aimarket-plugins`).

## Configure (env)

| var | meaning |
|-----|---------|
| `AIMARKET_METIS_URL` | Metis verify API base (default `https://metis.modelmarket.dev`) |
| `AIMARKET_METIS_KEY` | optional bearer for Metis verify |
| `AIMARKET_SEARCH_URL` | DuckDuckGo HTML endpoint override |
| `AIMARKET_MCP_KEY` | HTTP only — bearer auth key |
| `AIMARKET_MCP_PRODUCTION` | HTTP only — `1` requires `AIMARKET_MCP_KEY` (fail-closed) |
| `AIMARKET_MCP_RATE` | HTTP only — requests/min per key/IP (default 120) |
| `AIMARKET_MCP_PORT` | HTTP only — listen port (default 9090) |

## Run (stdio — Glama / Claude Desktop)

```bash
pip install -e .
python mcp_stdio_server.py
```

Claude Desktop (`mcpServers` entry):

```json
{
  "mcpServers": {
    "aimarket-mcp": {
      "command": "python",
      "args": ["mcp_stdio_server.py"],
      "cwd": "/path/to/aimarket-mcp"
    }
  }
}
```

Or via PyPI script: `aimarket-mcp`

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


Listing: **[glama.ai/mcp/servers/alexar76/aimarket-mcp](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)**

Same pattern as **[aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway)** (working on Glama): repo-root [`glama.json`](glama.json) + [`Dockerfile`](Dockerfile) + `python mcp_stdio_server.py`.

| Field | Value |
|-------|--------|
| **Dockerfile** | `Dockerfile` (from repo — **not** Glama debian/uv template) |
| **Command** | `python mcp_stdio_server.py` |
| **Placeholder parameters** | `{}` |
| **Pinned SHA** | empty (latest) |

**Do not use** the auto-generated `debian:trixie-slim` + `uv sync` + `mcp-proxy -- aimarket-mcp` template — that was the broken HTTP/ENOENT path.

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

## Glama

Glama **ignores** repo Dockerfiles — set **Build steps** in
[admin/dockerfile](https://glama.ai/mcp/servers/alexar76/aimarket-mcp/admin/dockerfile):

```json
["bash scripts/glama_install.sh"]
```

CMD: `[".venv/bin/python", "mcp_stdio_server.py"]`. Pin **`main`** or tag **`glama-build`** (not a
fixed SHA). Details: [`docs/GLAMA.md`](docs/GLAMA.md).

## Registries

| Registry | Listing |
|----------|---------|
| **Glama** | [glama.ai/mcp/servers/alexar76/aimarket-mcp](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) |
| **Official MCP Registry** | `io.github.alexar76/aimarket-mcp` — `server.json` + GitHub Actions |
| **PyPI** | `pip install aimarket-mcp` |
| **GitHub Releases** | [github.com/alexar76/aimarket-mcp/releases](https://github.com/alexar76/aimarket-mcp/releases) |

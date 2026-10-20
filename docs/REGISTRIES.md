# MCP directory checklist

Status checked on 2026-10-20. A repository manifest is not proof that a registry
has accepted or refreshed a release.

| Directory | Status | Listing / submission |
|---|---|---|
| Glama | Listed; working release 0.4.0 published, five tools inspected | [Listing and Admin](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) |
| Official MCP Registry | Manifest and publish workflow present; current remote version not reverified in this pass | [Registry](https://registry.modelcontextprotocol.io/) · [`server.json`](../server.json) |
| Smithery | Blocked: publishing returns 403, “Updating servers has been removed” | [Publish](https://smithery.ai/servers/new) · [Service transition](https://smithery.ai/future) |
| mcp.so | Manual submission pending; no confirmed listing recorded here | [Directory / submit entry point](https://mcp.so/) |
| PulseMCP | Manual submission pending; no confirmed listing recorded here | [Submit](https://www.pulsemcp.com/submit) |

## Assets to prepare

Use the same factual descriptions everywhere:

- **Name:** aimarket-mcp
- **Short description (under 160 characters):** Discover and invoke AI services with signed receipts, fetch public pages, search the web, and request Metis verification. Five MCP tools.
- **Repository:** `https://github.com/alexar76/aimarket-mcp`
- **Install:** `uvx aimarket-mcp`, or `pip install aimarket-mcp` then `aimarket-mcp`
- **License:** MIT
- **Icon:** supply a public project icon if the directory requests one; do not put credentials in an asset URL.
- **Configuration:** no credentials required for startup or tool discovery. See the README for optional service settings.

| Directory | Submission assets / checks |
|---|---|
| Glama | GitHub repository, maintainer in `glama.json`, short description; build and inspect before creating a release. Icon optional. |
| Official MCP Registry | Valid `server.json`, matching published package version, package metadata, and registry authentication. Use the repository's publish workflow. |
| Smithery | The current form requests a remote HTTP MCP URL; do not submit the stdio command as a URL. Publication is currently blocked. |
| mcp.so | Prepare repository URL, short description, install command, and an icon if requested by its submission flow. |
| PulseMCP | Prepare repository URL, short description, install instructions, and a public project icon if requested. |

## Before marking a submission complete

- [ ] Confirm the package version can initialize and return all five tools.
- [ ] Submit through the directory's current supported process.
- [ ] Record the resulting public listing URL and date here.
- [ ] Check that the public tool catalog matches the release.
- [ ] Never paste service keys or account tokens into listing text.

Smithery announced shutdown of its proxy and managed identity on October 31,
2026. Its remaining directory is curated; do not promise self-service publication
or working `run.tools` URLs after that date.

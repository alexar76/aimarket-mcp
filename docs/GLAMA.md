# Glama build — admin form & pinning

Listing: [glama.ai/mcp/servers/alexar76/aimarket-mcp](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)

Admin: […/admin/dockerfile](https://glama.ai/mcp/servers/alexar76/aimarket-mcp/admin/dockerfile)

## Glama does not use repo Dockerfiles

Glama **generates** its own image (debian + node + uv + clone into `/app`). Repo
[`Dockerfile.glama`](../Dockerfile.glama) is for local/self-host only. Configure the
**Build steps** field in admin — do not rely on auto-detected `uv pip install`.

### Form values (copy-paste)

| Field | Value |
|-------|-------|
| **Build steps** | `["bash scripts/glama_install.sh"]` |
| **CMD arguments** | `["mcp-proxy", "--", ".venv/bin/python", "-m", "aimarket_mcp.stdio_server"]` |
| **Pinned commit SHA** | empty — follows the latest synced commit |

Alternative build steps (manual venv — same as the script):

```json
["uv venv .venv", "uv pip install -r requirements-mcp.txt", "uv pip install --no-deps -e ."]
```

Do **not** use auto-detected or `--system` on Glama's Python 3.13 (PEP 668):

```text
uv pip install --system …              # fails: externally managed environment
uv pip install -r requirements-mcp.txt   # fails: no venv
pip install …                            # fails: No module named pip
```

### Common errors

| Log | Fix |
|-----|-----|
| `unable to read tree (15a1770…)` | Stale SHA pin → pin **`main`** or **`glama-build`**, Sync Server |
| `No virtual environment found` | Use [`scripts/glama_install.sh`](../scripts/glama_install.sh) (creates `.venv`) |
| `No module named pip` | Same — use the script (uv + venv), not plain `pip` |
| `externally managed environment` | Do not use `--system`; CMD must be `.venv/bin/python`, not `python` |

## Release and inspection

Repository sync refreshes the README and metadata; it does not replace a published
container release. After changing the startup command or source:

1. Sync the repository.
2. Build and check that MCP initialization and `tools/list` succeed.
3. Create a release from the successful test using the package version.
4. Check the public catalog contains all five tools, including
   `market_search_tool` and `market_invoke_tool`.
5. Check TDQS for that release; new tool evaluations can remain queued.

The mirror now preserves history. Leave the SHA field empty to follow new synced
commits. The old `mcp_stdio_server.py` entrypoint no longer exists: start the package
module with `-m aimarket_mcp.stdio_server`.

On 2026-10-20, correcting that command restored the Glama build and MCP inspection.
Release `0.4.0` was published successfully.

## Local Docker test

```bash
docker build -f Dockerfile.glama -t aimarket-mcp-glama .
docker run --rm -i aimarket-mcp-glama
```

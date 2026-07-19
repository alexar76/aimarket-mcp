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
| **CMD arguments** | `[".venv/bin/python", "mcp_stdio_server.py"]` |
| **Pinned commit SHA** | empty — use **`main`** or tag **`glama-build`** |

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

## Pinning (squashed mirror)

Force-pushed squashed mirror **deletes old commit SHAs** on each publish. Prefer
**`main`** or moving tag **`glama-build`**, not a fixed hash.

## Local Docker test

```bash
docker build -f Dockerfile.glama -t aimarket-mcp-glama .
docker run --rm -i aimarket-mcp-glama
```

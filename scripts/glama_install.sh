#!/usr/bin/env bash
# Glama admin → Build steps: ["bash scripts/glama_install.sh"]
# Glama debian + Python 3.13: no pip on system Python, PEP 668 blocks --system installs.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
  uv venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  uv pip install -r requirements-mcp.txt
  uv pip install --no-deps -e .
elif python3 -m pip --version >/dev/null 2>&1; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python3 -m pip install --no-cache-dir -r requirements-mcp.txt
  python3 -m pip install --no-deps -e .
else
  echo "glama_install.sh: need uv or python3 -m pip" >&2
  exit 1
fi

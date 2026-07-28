#!/usr/bin/env python3
"""Everything that must be true before aimarket-mcp is uploaded to PyPI.

    python3 scripts/prerelease.py              # build, then check the built wheel
    python3 scripts/prerelease.py --published  # check what PyPI is serving right now

Exit 0 means safe to publish. Nothing here talks to PyPI's upload API — it only builds,
installs into throwaway virtualenvs, and drives the result.

Why this exists: 0.2.0, 0.2.1 and 0.2.2 each shipped a defect found immediately after
upload, and each was invisible to the check that came before it.

  0.2.0  serverInfo announced the MCP SDK's version instead of ours. Reading the code
         could not see it — FastMCP fills the field in, and only a client that completes
         the initialize handshake is told what.
  0.2.1  market_invoke dropped source_hub and read `result` where the federated path
         answers `output`, so every federated capability returned null. Invisible until
         something federated actually existed to call.
  0.2.2  mcp 2.0.0 removed `mcp.server.fastmcp`, and the dependency said `<4`, so a fresh
         install pulled 2.0 and the console script died on import. Invisible to any test
         run in an environment whose resolver had already cached mcp 1.x.

So: a clean resolver, a real subprocess, a real protocol handshake, and a real federated
call — every time, not one new one per release.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TOOLS = {
    "web_fetch_tool",
    "web_search_tool",
    "metis_verify_tool",
    "market_search_tool",
    "market_invoke_tool",
}
# A federated capability on the public hub, with the ids market_search reports for it.
FEDERATED_PROBE = {
    "capability_id": "kantor.transport@v1",
    "product_id": "prod-kantor",
    "source_hub": "https://oracles.modelmarket.dev/family",
    "input": {"a": [0.5, 0.5], "b": [0.3, 0.7], "cost": [[0, 1], [1, 0]]},
}

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  {'OK  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)
    return ok


def declared_version() -> str:
    """Regex, not tomllib: this must run under whatever interpreter has `build` installed,
    which on this machine is a 3.9 that predates tomllib."""
    m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    if not m:
        raise SystemExit("no version in pyproject.toml")
    return m.group(1)


def tool_python(module: str) -> str:
    """An interpreter that actually has `module`. build/twine and the venv interpreter are
    not always the same one, and a release gate that cannot find its own tools is useless."""
    for cand in (sys.executable, "python3", "python"):
        exe = shutil.which(cand) or cand
        r = subprocess.run([exe, "-c", f"import {module}"], capture_output=True)
        if r.returncode == 0:
            return exe
    raise SystemExit(f"no interpreter with `{module}` — pip install {module}")


def check_versions_agree() -> str:
    """Four files carry the version and three of them once disagreed."""
    print("\n── version is one number ──")
    ver = declared_version()
    init = (ROOT / "aimarket_mcp" / "__init__.py").read_text()
    server_json = json.loads((ROOT / "server.json").read_text())
    check(f'__version__ = "{ver}"' in init, f"__init__.py == {ver}")
    check(server_json.get("version") == ver, f"server.json == {ver}", str(server_json.get("version")))
    for pkg in server_json.get("packages") or []:
        check(pkg.get("version") == ver, f"server.json packages[] == {ver}", str(pkg.get("version")))
    return ver


def build() -> Path:
    print("\n── build ──")
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    subprocess.run([tool_python("build"), "-m", "build"], cwd=ROOT, check=True, capture_output=True)
    wheels = sorted(dist.glob("*.whl"))
    check(len(wheels) == 1, "exactly one wheel built", f"{[w.name for w in wheels]}")
    r = subprocess.run([tool_python("twine"), "-m", "twine", "check", *map(str, dist.iterdir())],
                       capture_output=True, text=True)
    check("FAILED" not in r.stdout and r.returncode == 0, "twine check", r.stdout[-200:])
    return wheels[0]


def drive(venv: Path, ver: str, label: str) -> None:
    """Start the installed console script and speak MCP to it, as a host would."""
    driver = venv / "driver.py"
    driver.write_text(
        "import asyncio, json, sys\n"
        "from mcp import ClientSession, StdioServerParameters\n"
        "from mcp.client.stdio import stdio_client\n"
        "async def main():\n"
        "    async with stdio_client(StdioServerParameters(command='aimarket-mcp', args=[])) as (r, w):\n"
        "        async with ClientSession(r, w) as s:\n"
        "            init = await s.initialize()\n"
        "            tools = [t.name for t in (await s.list_tools()).tools]\n"
        "            search = (await s.call_tool('market_search_tool',\n"
        "                {'intent': 'optimal transport between distributions', 'limit': 2})).content[0].text\n"
        f"            probe = {FEDERATED_PROBE!r}\n"
        "            inv = (await s.call_tool('market_invoke_tool', probe)).content[0].text\n"
        "            print(json.dumps({'version': init.serverInfo.version, 'tools': tools,\n"
        "                              'search': search, 'invoke': inv}))\n"
        "asyncio.run(main())\n"
    )
    env_path = f"{venv / 'bin'}:{__import__('os').environ['PATH']}"
    r = subprocess.run([str(venv / "bin" / "python"), str(driver)],
                       capture_output=True, text=True, timeout=300,
                       env={**__import__("os").environ, "PATH": env_path})
    if r.returncode != 0:
        check(False, f"{label}: server runs over stdio", r.stderr.strip()[-300:])
        return
    out = json.loads(r.stdout.strip().splitlines()[-1])

    check(out["version"] == ver, f"{label}: serverInfo reports {ver}", out["version"])
    check(set(out["tools"]) == EXPECTED_TOOLS, f"{label}: five tools exposed",
          str(sorted(set(EXPECTED_TOOLS) ^ set(out["tools"]))))
    check("source_hub=" in out["search"], f"{label}: search surfaces source_hub")
    # The federated call is the one that matters: it exercises source_hub forwarding, the
    # output/result shape, and the live hub in one go.
    try:
        payload = json.loads(out["invoke"].replace("<untrusted>", "").replace("</untrusted>", ""))
    except json.JSONDecodeError:
        check(False, f"{label}: federated invoke returns JSON", out["invoke"][:200])
        return
    check(payload.get("success") is True, f"{label}: federated invoke succeeds", str(payload)[:200])
    check(payload.get("result") not in (None, {}), f"{label}: federated invoke returns a result",
          "result was null — the federated path answers `output`, not `result`")


def floor_pins() -> list[str]:
    """`pkg==<lower bound>` for every dependency that declares one.

    A `>=` is a promise that the package works with that version, and nobody had ever
    checked it: `pydantic>=2` was unsatisfiable, because mcp itself needs >=2.7.2, so any
    user who pinned pydantic 2.0 got ResolutionImpossible rather than a working install.
    An untested lower bound is not a constraint, it is a guess published as fact.
    """
    block = re.search(r"^dependencies = \[(.*?)^\]", (ROOT / "pyproject.toml").read_text(),
                      re.S | re.M).group(1)
    pins = []
    for raw in re.findall(r'"([^"]+)"', block):
        m = re.match(r"([A-Za-z0-9_.-]+)\s*>=\s*([0-9][^,\s]*)", raw)
        if m:
            pins.append(f"{m.group(1)}=={m.group(2)}")
    return pins


def in_clean_venv(spec: str, ver: str, label: str, extra: list[str] | None = None) -> None:
    """Install `spec` with a cold resolver. --no-cache-dir is the point: a warm cache hides
    a dependency release that breaks the package for everyone installing today."""
    print(f"\n── {label} ──")
    with tempfile.TemporaryDirectory() as tmp:
        venv = Path(tmp) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
        r = subprocess.run([str(venv / "bin" / "pip"), "install", "-q", "--no-cache-dir",
                            spec, *(extra or [])],
                           capture_output=True, text=True, timeout=900)
        if not check(r.returncode == 0, f"{label}: pip install", r.stderr.strip()[-300:]):
            return
        drive(venv, ver, label)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--published", action="store_true",
                    help="check what PyPI serves now instead of the local build")
    ap.add_argument("--skip-floor", action="store_true",
                    help="skip the lowest-allowed-dependency run (slow; only for a quick retry)")
    args = ap.parse_args()

    ver = check_versions_agree()
    if args.published:
        in_clean_venv(f"aimarket-mcp=={ver}", ver, f"published {ver} from PyPI")
    else:
        wheel = build()
        # Ceiling: whatever the resolver picks today. This is what catches an upstream
        # major shipping between two releases — mcp 2.0.0 did, four hours after 0.2.2.
        in_clean_venv(str(wheel), ver, f"local wheel {ver}, newest deps")
        if not args.skip_floor:
            # Floor: the oldest versions the metadata claims to support.
            pins = floor_pins()
            in_clean_venv(str(wheel), ver, f"local wheel {ver}, oldest allowed deps", pins)
            print(f"    (floor: {', '.join(pins)})")

    print()
    if failures:
        print(f"NOT SAFE TO PUBLISH — {len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{ver} is safe to publish.  python3 -m twine upload dist/*")
    return 0


if __name__ == "__main__":
    sys.exit(main())

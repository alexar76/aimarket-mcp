"""aimarket-mcp — the alexar76 ecosystem MCP gateway (web fetch/search, Metis verify, …).

Speaks MCP Streamable-HTTP, hardened with SSRF protection + output sanitization. Consumed by
Metis and ARGUS via the `aimarket-web` ecosystem preset.
"""
# Single source of truth. `server.py` and `tools.py` import this instead of repeating a
# literal: the three had drifted to 0.1.0 / 0.1.0 / 0.1.4, so PyPI shipped 0.1.4 while
# every MCP client was told `serverInfo.version: 0.1.0`. Keep in step with
# pyproject.toml — that one cannot import Python.
__version__ = "0.2.3"

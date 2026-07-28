# aimarket-mcp — stdio MCP server for Glama / Claude Desktop
#
# Glama's builder may run `uv pip install` without creating a venv first.
# UV_SYSTEM_PYTHON=1 and `--system` satisfy both uv and plain pip fallbacks.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="aimarket-mcp"
LABEL org.opencontainers.image.description="alexar76 ecosystem MCP gateway — web fetch/search + Metis verify (stdio)"
LABEL ai-market.mcp="true"

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY requirements-mcp.txt pyproject.toml README.md LICENSE ./
COPY aimarket_mcp ./aimarket_mcp
COPY mcp_stdio_server.py ./

RUN pip install --no-cache-dir uv \
    && uv pip install --system -r requirements-mcp.txt \
    && uv pip install --system --no-deps -e .

ENTRYPOINT ["python", "mcp_stdio_server.py"]

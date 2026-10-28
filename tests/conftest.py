import pytest

@pytest.fixture(autouse=True)
def _no_kernel_socket_table(monkeypatch):
    """ASGI callers are synthetic sockets; keep secure defaults unless a test opts in."""
    from aimarket_mcp import server as socket_auth

    monkeypatch.setattr(socket_auth, "_PROC_NET_TCP", ())
    monkeypatch.delenv("AIMARKET_MCP_LOCAL_RELAY", raising=False)
    monkeypatch.delenv("AIMARKET_MCP_LOCAL_UNVERIFIED", raising=False)


@pytest.fixture
def local_http_opt_in(monkeypatch):
    """Explicit test operator choice for protocol tests without real kernel sockets."""
    monkeypatch.setenv("AIMARKET_MCP_LOCAL_RELAY", "1")
    monkeypatch.setenv("AIMARKET_MCP_LOCAL_UNVERIFIED", "1")

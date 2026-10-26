import pytest

from aimarket_mcp import server


@pytest.fixture(autouse=True)
def _no_kernel_socket_table(monkeypatch):
    """The tests fake loopback callers that are not real sockets, so the kernel's table would
    never show them on Linux. Each test sees what macOS sees, no table, unless it sets one."""
    monkeypatch.setattr(server, "_PROC_NET_TCP", ())

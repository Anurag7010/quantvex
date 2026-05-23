"""
Global pytest configuration for the QuantVex test suite.

Provides:
- memgraph_reachable(): probe whether Memgraph is accepting Bolt connections.
- Auto-skip logic for @pytest.mark.integration tests.
"""
from __future__ import annotations

import socket
import pytest


def _memgraph_reachable() -> bool:
    """Return True only when Memgraph is accepting Bolt connections on port 7687."""
    try:
        with socket.create_connection(("127.0.0.1", 7687), timeout=2):
            return True
    except OSError:
        return False


_MEMGRAPH_UP = _memgraph_reachable()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from mcp_server.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def pytest_collection_modifyitems(config, items):
    """
    Automatically skip any test marked @pytest.mark.integration when
    Memgraph is not reachable, instead of erroring during fixture setup.
    """
    if _MEMGRAPH_UP:
        return

    skip_no_graph = pytest.mark.skip(
        reason="Memgraph not reachable — start docker/memgraph-docker-compose.yml"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_no_graph)

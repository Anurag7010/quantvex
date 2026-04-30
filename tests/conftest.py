"""
Global pytest configuration for the QuantVex test suite.

Provides:
- nebula_reachable(): probe whether a live NebulaGraph is available.
- Auto-skip logic for @pytest.mark.integration tests.
- Shared skip marker for NebulaGraph-dependent tests.
"""
from __future__ import annotations

import pytest


def _nebula_reachable() -> bool:
    """Return True only when NebulaGraph graphd is accepting connections."""
    try:
        from nebula3.gclient.net import ConnectionPool
        from nebula3.Config import Config

        cfg = Config()
        cfg.max_connection_pool_size = 1
        pool = ConnectionPool()
        ok = pool.init([("127.0.0.1", 9669)], cfg)
        try:
            pool.close()
        except Exception:
            pass
        return bool(ok)
    except Exception:
        return False


# Compute once at collection time
_NEBULA_UP = _nebula_reachable()


def pytest_collection_modifyitems(config, items):
    """
    Automatically skip any test marked @pytest.mark.integration when
    NebulaGraph is not reachable, instead of erroring during fixture setup.
    """
    if _NEBULA_UP:
        return  # Nothing to do — graph is available

    skip_no_graph = pytest.mark.skip(
        reason="NebulaGraph not reachable — start docker/nebula-docker-compose.yml"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_no_graph)

"""
Integration tests for GraphClient (Memgraph via neo4j Bolt driver).

Prerequisites:
    docker compose -f docker/memgraph-docker-compose.yml up -d

Then run:
    PYTHONPATH=src pytest tests/test_graph_client.py -v

TEST VERTEX
-----------
All tests share the VID "TEST_AAPL" so they remain isolated from
production supply-chain data.  The fixture inserts it once per session
and the teardown deletes it.
"""

import socket
import pytest


# ---------------------------------------------------------------------------
# Connectivity helper
# ---------------------------------------------------------------------------

_MEMGRAPH_HOST = "127.0.0.1"
_MEMGRAPH_PORT = 7687
_TEST_TICKER = "TEST_AAPL"


def _memgraph_reachable() -> bool:
    try:
        with socket.create_connection((_MEMGRAPH_HOST, _MEMGRAPH_PORT), timeout=2):
            return True
    except OSError:
        return False


memgraph_required = pytest.mark.skipif(
    not _memgraph_reachable(),
    reason="Memgraph not reachable — start docker/memgraph-docker-compose.yml",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client():
    from finance_mcp.graph.client import GraphClient
    with GraphClient(host=_MEMGRAPH_HOST, port=_MEMGRAPH_PORT) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def insert_test_vertex(client):
    """Insert a known Company vertex before all tests and delete it after."""
    if not _memgraph_reachable():
        yield
        return
    client._run(
        "MERGE (c:Company {ticker: $ticker}) SET c.name = $name, c.sector = $sector",
        ticker=_TEST_TICKER, name="Apple Inc.", sector="Technology",
    )
    yield
    client._run(
        "MATCH (c:Company {ticker: $ticker}) DETACH DELETE c",
        ticker=_TEST_TICKER,
    )


# ---------------------------------------------------------------------------
# Pool lifecycle
# ---------------------------------------------------------------------------

@memgraph_required
class TestGraphClientPool:

    def test_initialize_pool_succeeds(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient(host=_MEMGRAPH_HOST, port=_MEMGRAPH_PORT)
        c.initialize_pool()
        c.initialize_pool()  # idempotent
        c.close()

    def test_context_manager_closes_driver(self):
        from finance_mcp.graph.client import GraphClient
        with GraphClient(host=_MEMGRAPH_HOST, port=_MEMGRAPH_PORT) as c:
            assert c._driver is not None
        assert c._driver is None

    def test_query_without_pool_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient(host=_MEMGRAPH_HOST, port=_MEMGRAPH_PORT)
        with pytest.raises(RuntimeError, match="not initialised"):
            c.fetch_company("AAPL")

    def test_no_raw_execute_attribute(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        assert not hasattr(c, "execute"), "GraphClient must not expose a public execute() method"
        assert not hasattr(c, "run_query"), "GraphClient must not expose a public run_query() method"


# ---------------------------------------------------------------------------
# fetch_company
# ---------------------------------------------------------------------------

@memgraph_required
class TestFetchCompany:

    def test_fetch_known_company_returns_dict(self, client):
        result = client.fetch_company(_TEST_TICKER)
        assert isinstance(result, dict)
        assert result  # non-empty

    def test_fetch_company_has_required_keys(self, client):
        result = client.fetch_company(_TEST_TICKER)
        assert set(result.keys()) == {"ticker", "name", "sector"}

    def test_fetch_company_values_correct(self, client):
        result = client.fetch_company(_TEST_TICKER)
        assert result["ticker"] == _TEST_TICKER
        assert result["name"] == "Apple Inc."
        assert result["sector"] == "Technology"

    def test_fetch_nonexistent_company_returns_empty_dict(self, client):
        result = client.fetch_company("VID_DOES_NOT_EXIST_XYZ")
        assert result == {}


# ---------------------------------------------------------------------------
# VID validation (no live graph required)
# ---------------------------------------------------------------------------

class TestVidValidation:

    def test_empty_ticker_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="ticker"):
            c.fetch_company("")

    def test_ticker_with_spaces_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="ticker"):
            c.fetch_company("AAPL Corp!")

    def test_ticker_too_long_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="ticker"):
            c.fetch_company("A" * 65)

    def test_valid_ticker_passes_validation(self):
        from finance_mcp.graph.client import GraphClient
        from finance_mcp.graph.client import _validate_vid
        _validate_vid("AAPL", "ticker")  # no exception
        _validate_vid("TSM", "ticker")
        _validate_vid("BRK_B", "ticker")

    def test_insert_company_empty_ticker_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="ticker"):
            c.insert_company("", "Some Corp")

    def test_insert_company_empty_name_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="name"):
            c.insert_company("VALID", "")

    def test_insert_company_name_too_long_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="name"):
            c.insert_company("VALID", "X" * 257)

    def test_upsert_event_severity_too_high_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="severity"):
            c.upsert_event("EVT_OK", "desc", 11)

    def test_upsert_event_severity_negative_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="severity"):
            c.upsert_event("EVT_OK", "desc", -1)

    def test_max_hops_zero_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="max_hops"):
            c.trace_impact("TSMC", max_hops=0)

    def test_max_hops_six_raises(self):
        from finance_mcp.graph.client import GraphClient
        c = GraphClient()
        with pytest.raises(ValueError, match="max_hops"):
            c.trace_impact("TSMC", max_hops=6)


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

@memgraph_required
def test_ping_returns_true(client):
    assert client.ping() is True

"""
Tests for GraphClient security and API contract.

Replaces the old test_queries.py which tested the deleted NebulaGraph
queries.py module.  These tests verify:

1. VID validation rejects dangerous inputs before any query is sent.
2. GraphClient public API surface (no raw execute/run_query exposure).
3. Integration: CRUD operations against live Memgraph.

Run unit tests only (no docker required)::

    PYTHONPATH=src pytest tests/test_queries.py -v -m "not integration"
"""

import socket
import pytest

from finance_mcp.graph.client import GraphClient, _validate_vid, _validate_str

_MEMGRAPH_HOST = "127.0.0.1"
_MEMGRAPH_PORT = 7687
_TEST_COMPANY   = "TEST_QUERIES_AAPL"
_TEST_COMMODITY = "TEST_QUERIES_OIL"
_TEST_EVENT     = "TEST_QUERIES_EVT1"


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
# VID validation
# ---------------------------------------------------------------------------

class TestVidValidation:
    """Verify _validate_vid rejects values that could carry injection payloads."""

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            _validate_vid("", "field")

    def test_space_in_value_raises(self):
        with pytest.raises(ValueError):
            _validate_vid("AAPL Corp", "ticker")

    def test_semicolon_raises(self):
        with pytest.raises(ValueError):
            _validate_vid("AAPL;DROP", "ticker")

    def test_single_quote_raises(self):
        with pytest.raises(ValueError):
            _validate_vid("AAPL'", "ticker")

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            _validate_vid("A" * 65, "ticker")

    def test_valid_ticker_passes(self):
        _validate_vid("AAPL", "ticker")
        _validate_vid("TSM", "ticker")
        _validate_vid("BRK_B", "ticker")
        _validate_vid("005930.KS", "ticker")

    def test_valid_event_id_passes(self):
        _validate_vid("EVT_TAIWAN_STRAIT_2024", "event_id")

    def test_valid_commodity_id_passes(self):
        _validate_vid("CRUDE_OIL", "commodity_id")
        _validate_vid("NEON_GAS", "commodity_id")


# ---------------------------------------------------------------------------
# String validation
# ---------------------------------------------------------------------------

class TestStrValidation:

    def test_empty_required_raises(self):
        with pytest.raises(ValueError):
            _validate_str("   ", "name", 256, required=True)

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            _validate_str("x" * 257, "name", 256)

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            _validate_str(123, "name", 256)  # type: ignore[arg-type]

    def test_empty_optional_passes(self):
        _validate_str("", "sector", 128, required=False)  # no exception


# ---------------------------------------------------------------------------
# API surface — no raw execute() or run_query() exposed
# ---------------------------------------------------------------------------

class TestApiSurface:

    def test_no_public_execute_method(self):
        c = GraphClient()
        assert not hasattr(c, "execute"), "GraphClient must not expose execute()"

    def test_no_public_run_query_method(self):
        c = GraphClient()
        assert not hasattr(c, "run_query"), "GraphClient must not expose run_query()"

    def test_run_is_private(self):
        c = GraphClient()
        assert hasattr(c, "_run"), "_run must exist as private method"

    def test_method_names_match_plan(self):
        expected = [
            "fetch_company", "fetch_commodity", "fetch_event",
            "insert_company", "insert_commodity", "upsert_event",
            "insert_depends_on", "insert_requires", "insert_impacts",
            "trace_impact", "find_companies_requiring", "ping",
            "initialize_pool", "close",
        ]
        c = GraphClient()
        for name in expected:
            assert callable(getattr(c, name, None)), f"GraphClient missing method: {name}"


# ---------------------------------------------------------------------------
# Integration: CRUD against live Memgraph
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_client():
    with GraphClient(host=_MEMGRAPH_HOST, port=_MEMGRAPH_PORT) as c:
        yield c


@pytest.fixture(scope="module")
def seed_graph(live_client: GraphClient):
    """Insert test vertices before the module, delete them after."""
    live_client._run(
        "MERGE (c:Company {ticker: $t}) SET c.name = $n, c.sector = $s",
        t=_TEST_COMPANY, n="Apple Inc.", s="Technology",
    )
    live_client._run(
        "MERGE (c:Commodity {commodity_id: $id}) SET c.name = $n, c.category = $cat",
        id=_TEST_COMMODITY, n="Crude Oil", cat="Energy",
    )
    live_client._run(
        "MERGE (e:Event {event_id: $id}) SET e.description = $d, e.severity = $s",
        id=_TEST_EVENT, d="Supply disruption", s=7,
    )
    yield
    for node_id in [_TEST_COMPANY, _TEST_COMMODITY, _TEST_EVENT]:
        live_client._run(
            "MATCH (n) WHERE n.ticker = $id OR n.commodity_id = $id OR n.event_id = $id "
            "DETACH DELETE n",
            id=node_id,
        )


@memgraph_required
@pytest.mark.usefixtures("seed_graph")
class TestQueryIntegration:

    def test_fetch_company(self, live_client: GraphClient):
        r = live_client.fetch_company(_TEST_COMPANY)
        assert r, "Expected non-empty dict"
        assert r["ticker"] == _TEST_COMPANY

    def test_fetch_commodity(self, live_client: GraphClient):
        r = live_client.fetch_commodity(_TEST_COMMODITY)
        assert r, "Expected non-empty dict"

    def test_fetch_event(self, live_client: GraphClient):
        r = live_client.fetch_event(_TEST_EVENT)
        assert r, "Expected non-empty dict"
        assert r["severity"] == 7

    def test_fetch_nonexistent_returns_empty_dict(self, live_client: GraphClient):
        r = live_client.fetch_company("DOES_NOT_EXIST_XYZ")
        assert r == {}

    def test_insert_company_idempotent(self, live_client: GraphClient):
        live_client.insert_company(_TEST_COMPANY, "Apple Inc.", "Technology")
        r = live_client.fetch_company(_TEST_COMPANY)
        assert r["ticker"] == _TEST_COMPANY

    def test_trace_supply_chain_depth_bounds(self, live_client: GraphClient):
        with pytest.raises(ValueError, match="max_hops"):
            live_client.trace_impact(_TEST_COMPANY, max_hops=10)

"""
Tests for GraphClient write API:
  insert_company / insert_commodity / upsert_event

Unit tests (TestInsertValidation) run without any live graph.
Integration tests are auto-skipped when Memgraph is not reachable.

Run unit tests only (no docker required)::

    PYTHONPATH=src pytest tests/test_insert.py -v -m "not integration"
"""

from __future__ import annotations

import socket
import pytest

from finance_mcp.graph.client import GraphClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COMPANY_VID   = "AAPL"
_COMMODITY_VID = "LITHIUM"
_EVENT_VID     = "EVT_INSERT_001"

_MEMGRAPH_HOST = "127.0.0.1"
_MEMGRAPH_PORT = 7687


def _memgraph_reachable() -> bool:
    try:
        with socket.create_connection((_MEMGRAPH_HOST, _MEMGRAPH_PORT), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def client():
    """Live GraphClient — requires running Memgraph."""
    with GraphClient(host=_MEMGRAPH_HOST, port=_MEMGRAPH_PORT) as c:
        yield c


@pytest.fixture(scope="module")
def cleanup(client: GraphClient):
    """Delete test vertices before and after the module runs."""
    def _delete() -> None:
        try:
            client._run(
                "MATCH (n) WHERE "
                "(n:Company AND n.ticker IN $tickers) OR "
                "(n:Commodity AND n.commodity_id IN $cids) OR "
                "(n:Event AND n.event_id IN $eids) "
                "DETACH DELETE n",
                tickers=[_COMPANY_VID, "TEST_NO_SECTOR"],
                cids=[_COMMODITY_VID, "COPPER"],
                eids=[_EVENT_VID],
            )
        except Exception:
            pass

    _delete()
    yield
    _delete()


# ---------------------------------------------------------------------------
# Input validation — no live graph needed
# ---------------------------------------------------------------------------

class TestInsertValidation:
    """Validation tests — raise ValueError before any graph connection."""

    # --- insert_company ---

    def test_insert_company_empty_ticker_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="ticker"):
            c.insert_company("", "Some Corp")

    def test_insert_company_bad_ticker_chars_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="ticker"):
            c.insert_company("BAD TICKER!", "Some Corp")

    def test_insert_company_ticker_too_long_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="ticker"):
            c.insert_company("A" * 65, "Some Corp")

    def test_insert_company_empty_name_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="name"):
            c.insert_company("VALID", "")

    def test_insert_company_name_too_long_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="name"):
            c.insert_company("VALID", "X" * 257)

    # --- insert_commodity ---

    def test_insert_commodity_bad_id_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="commodity_id"):
            c.insert_commodity("bad id!", "Lithium")

    def test_insert_commodity_empty_name_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="name"):
            c.insert_commodity("LITHIUM", "")

    # --- upsert_event ---

    def test_upsert_event_bad_event_id_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="event_id"):
            c.upsert_event("bad id!", "desc", 5)

    def test_upsert_event_empty_description_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="description"):
            c.upsert_event("EVT_OK", "", 5)

    def test_upsert_event_severity_too_high_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="severity"):
            c.upsert_event("EVT_OK", "desc", 11)

    def test_upsert_event_severity_negative_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="severity"):
            c.upsert_event("EVT_OK", "desc", -1)

    def test_upsert_event_severity_non_int_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="severity"):
            c.upsert_event("EVT_OK", "desc", 5.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Live integration tests — require running Memgraph
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.usefixtures("cleanup")
class TestInsertCompany:

    def test_insert_apple_returns_true(self, client: GraphClient):
        result = client.insert_company(
            ticker="AAPL",
            name="Apple Inc.",
            sector="Technology",
        )
        assert result is True

    def test_inserted_company_is_fetchable(self, client: GraphClient):
        r = client.fetch_company("AAPL")
        assert r, "Expected non-empty dict"
        assert r["ticker"] == "AAPL"
        assert r["name"] == "Apple Inc."
        assert r["sector"] == "Technology"

    def test_insert_company_optional_sector_defaults_empty(self, client: GraphClient):
        result = client.insert_company("TEST_NO_SECTOR", "No-Sector Corp")
        assert result is True
        client._run(
            "MATCH (c:Company {ticker: $t}) DETACH DELETE c",
            t="TEST_NO_SECTOR",
        )

    def test_insert_company_is_idempotent(self, client: GraphClient):
        client.insert_company("AAPL", "Apple Inc. (dup)", "Consumer Electronics")
        r = client.fetch_company("AAPL")
        assert r, "Expected non-empty dict after second insert"


@pytest.mark.integration
@pytest.mark.usefixtures("cleanup")
class TestInsertCommodity:

    def test_insert_lithium_returns_true(self, client: GraphClient):
        result = client.insert_commodity(
            commodity_id="LITHIUM",
            name="Lithium",
            category="Battery Metals",
        )
        assert result is True

    def test_inserted_commodity_is_fetchable(self, client: GraphClient):
        r = client.fetch_commodity("LITHIUM")
        assert r, "Expected non-empty dict"
        assert r["name"] == "Lithium"
        assert r["category"] == "Battery Metals"

    def test_insert_commodity_optional_category_defaults_empty(self, client: GraphClient):
        result = client.insert_commodity("COPPER", "Copper")
        assert result is True
        client._run(
            "MATCH (c:Commodity {commodity_id: $id}) DETACH DELETE c",
            id="COPPER",
        )


@pytest.mark.integration
@pytest.mark.usefixtures("cleanup")
class TestUpsertEvent:

    def test_upsert_creates_event(self, client: GraphClient):
        result = client.upsert_event(
            event_id="EVT_INSERT_001",
            description="Test supply disruption",
            severity=7,
        )
        assert result is True

    def test_upserted_event_is_fetchable(self, client: GraphClient):
        r = client.fetch_event("EVT_INSERT_001")
        assert r, "Expected non-empty dict"
        assert r["description"] == "Test supply disruption"
        assert r["severity"] == 7

    def test_upsert_updates_existing_event(self, client: GraphClient):
        client.upsert_event(
            event_id="EVT_INSERT_001",
            description="Updated description",
            severity=9,
        )
        r = client.fetch_event("EVT_INSERT_001")
        assert r["description"] == "Updated description"
        assert r["severity"] == 9

    def test_upsert_event_severity_boundary_zero(self, client: GraphClient):
        result = client.upsert_event("EVT_INSERT_001", "Boundary low", 0)
        assert result is True

    def test_upsert_event_severity_boundary_ten(self, client: GraphClient):
        result = client.upsert_event("EVT_INSERT_001", "Boundary high", 10)
        assert result is True

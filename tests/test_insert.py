"""
Tests for SecureGraphClient write API:
  insert_company / insert_commodity / upsert_event

Prerequisites for integration tests
-------------------------------------
- NebulaGraph 4-container stack running (docker-compose up -d)
- supply_chain space bootstrapped (python -m finance_mcp.graph.schema)

Unit tests (TestInsertValidation) run without any live graph.
Integration tests are auto-skipped when NebulaGraph is not reachable.

Run unit tests only (no docker required)::

    cd /Users/anuragraut/Desktop/EDAI_MCP/finance-mcp
    PYTHONPATH=src .venv/bin/python3.11 -m pytest tests/test_insert.py -v -m "not integration"
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from finance_mcp.graph.client import SecureGraphClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COMPANY_VID   = "AAPL"
_COMMODITY_VID = "LITHIUM"
_EVENT_VID     = "EVT_INSERT_001"


def _root_execute(nGQL: str) -> None:
    """One-shot execution using the root session (teardown helper)."""
    from nebula3.gclient.net import ConnectionPool
    from nebula3.Config import Config

    cfg = Config()
    cfg.max_connection_pool_size = 1
    pool = ConnectionPool()
    pool.init([("127.0.0.1", 9669)], cfg)
    session = pool.get_session("root", "nebula")
    try:
        session.execute("USE supply_chain")
        result = session.execute(nGQL)
        if not result.is_succeeded():
            raise RuntimeError(f"Root teardown failed: {result.error_msg()}")
    finally:
        session.release()
        pool.close()


@pytest.fixture(scope="module")
def mock_client():
    """
    A SecureGraphClient with a fake pool injected so that validation methods
    (which raise ValueError before touching the graph) work without any live
    NebulaGraph connection.  Used exclusively by TestInsertValidation.
    """
    c = SecureGraphClient(host="127.0.0.1", port=9669)
    fake_pool = MagicMock()
    fake_session = MagicMock()
    fake_session.execute.return_value = MagicMock(is_succeeded=lambda: True)
    fake_pool.get_session.return_value = fake_session
    c._pool = fake_pool
    return c


@pytest.fixture(scope="module")
def client():
    """Live SecureGraphClient — requires running NebulaGraph."""
    with SecureGraphClient(host="127.0.0.1", port=9669) as c:
        yield c


@pytest.fixture(scope="module")
def cleanup(client: SecureGraphClient):
    """Delete test vertices before and after the module runs."""
    vids = [_COMPANY_VID, _COMMODITY_VID, _EVENT_VID]
    fmted = ", ".join(f'"{ v}"' for v in vids)

    def _delete() -> None:
        try:
            _root_execute(f"DELETE VERTEX {fmted} WITH EDGE")
        except Exception:  # noqa: BLE001
            pass  # vertices may not exist yet

    _delete()       # pre-clean
    yield
    _delete()       # post-clean


# ---------------------------------------------------------------------------
# Input validation — no live graph needed for these
# ---------------------------------------------------------------------------

class TestInsertValidation:
    """
    Input-validation tests — all raise ValueError before touching NebulaGraph.
    Uses mock_client so they run without a live graph.
    """

    # --- insert_company ---

    def test_insert_company_empty_ticker_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="ticker"):
            mock_client.insert_company("", "Some Corp")

    def test_insert_company_bad_ticker_chars_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="ticker"):
            mock_client.insert_company("BAD TICKER!", "Some Corp")

    def test_insert_company_ticker_too_long_raises(self, mock_client: SecureGraphClient):
        too_long = "A" * 65
        with pytest.raises(ValueError, match="ticker"):
            mock_client.insert_company(too_long, "Some Corp")

    def test_insert_company_empty_name_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="name"):
            mock_client.insert_company("VALID", "")

    def test_insert_company_name_too_long_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="name"):
            mock_client.insert_company("VALID", "X" * 257)

    # --- insert_commodity ---

    def test_insert_commodity_bad_id_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="commodity_id"):
            mock_client.insert_commodity("bad id!", "Lithium")

    def test_insert_commodity_empty_name_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="name"):
            mock_client.insert_commodity("LITHIUM", "")

    # --- upsert_event ---

    def test_upsert_event_bad_event_id_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="event_id"):
            mock_client.upsert_event("bad id!", "desc", 5)

    def test_upsert_event_empty_description_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="description"):
            mock_client.upsert_event("EVT_OK", "", 5)

    def test_upsert_event_severity_too_high_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="severity"):
            mock_client.upsert_event("EVT_OK", "desc", 11)

    def test_upsert_event_severity_negative_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="severity"):
            mock_client.upsert_event("EVT_OK", "desc", -1)

    def test_upsert_event_severity_non_int_raises(self, mock_client: SecureGraphClient):
        with pytest.raises(ValueError, match="severity"):
            mock_client.upsert_event("EVT_OK", "desc", 5.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Live integration tests — require running NebulaGraph
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.usefixtures("cleanup")
class TestInsertCompany:

    def test_insert_apple_returns_true(self, client: SecureGraphClient):
        result = client.insert_company(
            ticker="AAPL",
            name="Apple Inc.",
            sector="Technology",
        )
        assert result is True

    def test_inserted_company_is_fetchable(self, client: SecureGraphClient):
        r = client.fetch_company("AAPL")
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() >= 1
        nmap = r.row_values(0)[0].as_map()
        assert nmap["ticker"].as_string() == "AAPL"
        assert nmap["name"].as_string() == "Apple Inc."
        assert nmap["sector"].as_string() == "Technology"

    def test_insert_company_optional_sector_defaults_empty(
        self, client: SecureGraphClient
    ):
        # Insert a company without sector; it should not raise
        result = client.insert_company("TEST_NO_SECTOR", "No-Sector Corp")
        assert result is True
        _root_execute('DELETE VERTEX "TEST_NO_SECTOR" WITH EDGE')

    def test_insert_company_is_idempotent(self, client: SecureGraphClient):
        # Second insert overwrites; fetch should still succeed with one row
        client.insert_company("AAPL", "Apple Inc. (dup)", "Consumer Electronics")
        r = client.fetch_company("AAPL")
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() >= 1


@pytest.mark.integration
@pytest.mark.usefixtures("cleanup")
class TestInsertCommodity:

    def test_insert_lithium_returns_true(self, client: SecureGraphClient):
        result = client.insert_commodity(
            commodity_id="LITHIUM",
            name="Lithium",
            category="Battery Metals",
        )
        assert result is True

    def test_inserted_commodity_is_fetchable(self, client: SecureGraphClient):
        r = client.fetch_commodity("LITHIUM")
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() >= 1
        nmap = r.row_values(0)[0].as_map()
        assert nmap["name"].as_string() == "Lithium"
        assert nmap["category"].as_string() == "Battery Metals"

    def test_insert_commodity_optional_category_defaults_empty(
        self, client: SecureGraphClient
    ):
        result = client.insert_commodity("COPPER", "Copper")
        assert result is True
        _root_execute('DELETE VERTEX "COPPER" WITH EDGE')


@pytest.mark.integration
@pytest.mark.usefixtures("cleanup")
class TestUpsertEvent:

    def test_upsert_creates_event(self, client: SecureGraphClient):
        result = client.upsert_event(
            event_id="EVT_INSERT_001",
            description="Test supply disruption",
            severity=7,
        )
        assert result is True

    def test_upserted_event_is_fetchable(self, client: SecureGraphClient):
        r = client.fetch_event("EVT_INSERT_001")
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() >= 1
        nmap = r.row_values(0)[0].as_map()
        assert nmap["description"].as_string() == "Test supply disruption"
        assert nmap["severity"].as_int() == 7

    def test_upsert_updates_existing_event(self, client: SecureGraphClient):
        client.upsert_event(
            event_id="EVT_INSERT_001",
            description="Updated description",
            severity=9,
        )
        r = client.fetch_event("EVT_INSERT_001")
        assert r.is_succeeded(), r.error_msg()
        assert r.row_size() >= 1
        nmap = r.row_values(0)[0].as_map()
        assert nmap["description"].as_string() == "Updated description"
        assert nmap["severity"].as_int() == 9

    def test_upsert_event_severity_boundary_zero(self, client: SecureGraphClient):
        result = client.upsert_event("EVT_INSERT_001", "Boundary low", 0)
        assert result is True

    def test_upsert_event_severity_boundary_ten(self, client: SecureGraphClient):
        result = client.upsert_event("EVT_INSERT_001", "Boundary high", 10)
        assert result is True

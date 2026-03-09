"""
Integration tests for SecureGraphClient.trace_impact()

Graph topology used in this module
-----------------------------------
                    TSMC_TI (target — semiconductor foundry)
                    ↑               ↑
         AAPL_TI              NVDA_TI
         (1-hop)               (1-hop)
             ↑
        DELL_TI
        (2-hop from TSMC_TI via AAPL_TI)

Edges (all DEPENDS_ON, direction = dependent → supplier):
    AAPL_TI  → TSMC_TI   weight 0.9
    NVDA_TI  → TSMC_TI   weight 0.8
    DELL_TI  → AAPL_TI   weight 0.7

A TSMC shock (max_hops=1) should surface AAPL_TI + NVDA_TI.
A TSMC shock (max_hops=2) should additionally surface DELL_TI.

Run
---
    cd /Users/anuragraut/Desktop/EDAI_MCP/finance-mcp
    PYTHONPATH=src .venv/bin/python3.11 -m pytest tests/test_trace_impact.py -v
"""

from __future__ import annotations

import pytest
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

from finance_mcp.graph.client import SecureGraphClient

# ---------------------------------------------------------------------------
# Test VIDs  (suffix _TI avoids any clash with other test modules)
# ---------------------------------------------------------------------------
_TSMC   = "TSMC_TI"
_AAPL   = "AAPL_TI"
_NVDA   = "NVDA_TI"
_DELL   = "DELL_TI"
_ALL    = [_TSMC, _AAPL, _NVDA, _DELL]


def _root_exec(stmt: str) -> None:
    """One-shot root session helper used for seeding and teardown."""
    cfg = Config()
    cfg.max_connection_pool_size = 1
    pool = ConnectionPool()
    pool.init([("127.0.0.1", 9669)], cfg)
    session = pool.get_session("root", "nebula")
    try:
        session.execute("USE supply_chain")
        r = session.execute(stmt)
        if not r.is_succeeded():
            raise RuntimeError(f"seed/teardown failed: {r.error_msg()}")
    finally:
        session.release()
        pool.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    with SecureGraphClient(host="127.0.0.1", port=9669) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def seed_graph():
    """Insert TSMC shock topology before any test in this module runs."""
    vids_csv = ", ".join(f'"{v}"' for v in _ALL)

    # Clean any stale data from a previous run
    try:
        _root_exec(f"DELETE VERTEX {vids_csv} WITH EDGE")
    except RuntimeError:
        pass  # vertices may not exist yet

    _root_exec(
        f'INSERT VERTEX Company(ticker, name, sector) '
        f'VALUES '
        f'  "{_TSMC}":("TSMC",  "Taiwan Semiconductor Mfg.", "Technology"), '
        f'  "{_AAPL}":("AAPL",  "Apple Inc.",                "Technology"), '
        f'  "{_NVDA}":("NVDA",  "NVIDIA Corp.",              "Technology"), '
        f'  "{_DELL}":("DELL",  "Dell Technologies",         "Technology")'
    )
    # 1-hop dependents of TSMC
    _root_exec(
        f'INSERT EDGE DEPENDS_ON(weight) '
        f'VALUES '
        f'  "{_AAPL}"->"{_TSMC}":(0.9), '
        f'  "{_NVDA}"->"{_TSMC}":(0.8)'
    )
    # 2-hop dependent chain: DELL → AAPL → TSMC
    _root_exec(
        f'INSERT EDGE DEPENDS_ON(weight) '
        f'VALUES "{_DELL}"->"{_AAPL}":(0.7)'
    )

    yield

    # Teardown
    try:
        _root_exec(f"DELETE VERTEX {vids_csv} WITH EDGE")
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# Input validation (no live graph required — fails before _execute)
# ---------------------------------------------------------------------------

class TestTraceImpactValidation:

    def test_empty_ticker_raises(self, client: SecureGraphClient):
        with pytest.raises(ValueError, match="target_ticker"):
            client.trace_impact("")

    def test_invalid_ticker_chars_raises(self, client: SecureGraphClient):
        with pytest.raises(ValueError, match="target_ticker"):
            client.trace_impact("TSMC Corp!")

    def test_ticker_too_long_raises(self, client: SecureGraphClient):
        with pytest.raises(ValueError, match="target_ticker"):
            client.trace_impact("T" * 65)

    def test_max_hops_zero_raises(self, client: SecureGraphClient):
        with pytest.raises(ValueError, match="max_hops"):
            client.trace_impact("TSMC_TI", max_hops=0)

    def test_max_hops_too_large_raises(self, client: SecureGraphClient):
        with pytest.raises(ValueError, match="max_hops"):
            client.trace_impact("TSMC_TI", max_hops=6)

    def test_max_hops_non_int_raises(self, client: SecureGraphClient):
        with pytest.raises(ValueError, match="max_hops"):
            client.trace_impact("TSMC_TI", max_hops=2.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

class TestTraceImpactReturnType:

    def test_returns_list(self, client: SecureGraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        assert isinstance(result, list)

    def test_each_element_is_dict(self, client: SecureGraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        for item in result:
            assert isinstance(item, dict)

    def test_each_dict_has_required_keys(self, client: SecureGraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        for item in result:
            assert set(item.keys()) == {"ticker", "name", "sector"}

    def test_all_values_are_strings(self, client: SecureGraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        for item in result:
            assert isinstance(item["ticker"], str)
            assert isinstance(item["name"], str)
            assert isinstance(item["sector"], str)


# ---------------------------------------------------------------------------
# TSMC shock — correctness of propagation
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTraceTsmcShock:

    def test_no_impact_on_unknown_ticker(self, client: SecureGraphClient):
        result = client.trace_impact("UNKNOWN_TICKER_XYZ", max_hops=3)
        assert result == []

    def test_tsmc_shock_1hop_finds_direct_dependents(
        self, client: SecureGraphClient
    ):
        """Apple and NVIDIA depend directly on TSMC — both must appear."""
        result = client.trace_impact(_TSMC, max_hops=1)
        tickers = {r["ticker"] for r in result}
        assert _AAPL in tickers, f"AAPL_TI missing from 1-hop result: {tickers}"
        assert _NVDA in tickers, f"NVDA_TI missing from 1-hop result: {tickers}"

    def test_tsmc_shock_1hop_excludes_indirect(
        self, client: SecureGraphClient
    ):
        """DELL is 2 hops away — should NOT appear with max_hops=1."""
        result = client.trace_impact(_TSMC, max_hops=1)
        tickers = {r["ticker"] for r in result}
        assert _DELL not in tickers, (
            f"DELL_TI should be absent from 1-hop result but found in: {tickers}"
        )

    def test_tsmc_shock_2hop_finds_indirect_dependent(
        self, client: SecureGraphClient
    ):
        """DELL depends on AAPL which depends on TSMC — visible at 2 hops."""
        result = client.trace_impact(_TSMC, max_hops=2)
        tickers = {r["ticker"] for r in result}
        assert _DELL in tickers, f"DELL_TI missing from 2-hop result: {tickers}"

    def test_tsmc_shock_1hop_count(self, client: SecureGraphClient):
        """Exactly 2 distinct companies are 1-hop dependents of TSMC."""
        result = client.trace_impact(_TSMC, max_hops=1)
        assert len(result) == 2

    def test_tsmc_shock_2hop_count(self, client: SecureGraphClient):
        """3 distinct companies are within 2 hops of TSMC."""
        result = client.trace_impact(_TSMC, max_hops=2)
        assert len(result) == 3

    def test_result_tickers_are_deduplicated(self, client: SecureGraphClient):
        """DISTINCT in nGQL — no company should appear more than once."""
        result = client.trace_impact(_TSMC, max_hops=3)
        tickers = [r["ticker"] for r in result]
        assert len(tickers) == len(set(tickers)), (
            f"Duplicate tickers found: {tickers}"
        )

    def test_company_names_populated(self, client: SecureGraphClient):
        """name field must be a non-empty string for every record."""
        result = client.trace_impact(_TSMC, max_hops=2)
        for item in result:
            assert item["name"], f"Empty name for ticker {item['ticker']!r}"

    def test_max_hops_boundary_one_accepted(self, client: SecureGraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        assert isinstance(result, list)

    def test_max_hops_boundary_five_accepted(self, client: SecureGraphClient):
        result = client.trace_impact(_TSMC, max_hops=5)
        assert isinstance(result, list)

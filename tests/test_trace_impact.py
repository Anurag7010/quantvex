"""
Integration tests for GraphClient.trace_impact()

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
    PYTHONPATH=src pytest tests/test_trace_impact.py -v
"""

from __future__ import annotations

import socket
import pytest

from finance_mcp.graph.client import GraphClient

# ---------------------------------------------------------------------------
# Test VIDs
# ---------------------------------------------------------------------------
_TSMC = "TSMC_TI"
_AAPL = "AAPL_TI"
_NVDA = "NVDA_TI"
_DELL = "DELL_TI"
_ALL  = [_TSMC, _AAPL, _NVDA, _DELL]

_MEMGRAPH_HOST = "127.0.0.1"
_MEMGRAPH_PORT = 7687


def _memgraph_reachable() -> bool:
    try:
        with socket.create_connection((_MEMGRAPH_HOST, _MEMGRAPH_PORT), timeout=2):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Live GraphClient — requires running Memgraph."""
    with GraphClient(host=_MEMGRAPH_HOST, port=_MEMGRAPH_PORT) as c:
        yield c


@pytest.fixture(scope="module")
def seed_graph(client: GraphClient):
    """Insert TSMC shock topology before any test in this module runs."""

    # Clean stale data
    client._run(
        "MATCH (n) WHERE n.ticker IN $tickers DETACH DELETE n",
        tickers=_ALL,
    )

    # Vertices
    for ticker, name in [
        (_TSMC, "Taiwan Semiconductor Mfg."),
        (_AAPL, "Apple Inc."),
        (_NVDA, "NVIDIA Corp."),
        (_DELL, "Dell Technologies"),
    ]:
        client._run(
            "MERGE (c:Company {ticker: $ticker}) SET c.name = $name, c.sector = $sector",
            ticker=ticker, name=name, sector="Technology",
        )

    # DEPENDS_ON edges
    client._run(
        "MATCH (a:Company {ticker: $a}), (b:Company {ticker: $b}) "
        "MERGE (a)-[r:DEPENDS_ON]->(b) SET r.weight = $w",
        a=_AAPL, b=_TSMC, w=0.9,
    )
    client._run(
        "MATCH (a:Company {ticker: $a}), (b:Company {ticker: $b}) "
        "MERGE (a)-[r:DEPENDS_ON]->(b) SET r.weight = $w",
        a=_NVDA, b=_TSMC, w=0.8,
    )
    client._run(
        "MATCH (a:Company {ticker: $a}), (b:Company {ticker: $b}) "
        "MERGE (a)-[r:DEPENDS_ON]->(b) SET r.weight = $w",
        a=_DELL, b=_AAPL, w=0.7,
    )

    yield

    # Teardown
    client._run(
        "MATCH (n) WHERE n.ticker IN $tickers DETACH DELETE n",
        tickers=_ALL,
    )


# ---------------------------------------------------------------------------
# Input validation (no live graph required)
# ---------------------------------------------------------------------------

class TestTraceImpactValidation:
    """Validation tests — raise ValueError before touching Memgraph."""

    def test_empty_ticker_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="target_ticker"):
            c.trace_impact("")

    def test_invalid_ticker_chars_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="target_ticker"):
            c.trace_impact("TSMC Corp!")

    def test_ticker_too_long_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="target_ticker"):
            c.trace_impact("T" * 65)

    def test_max_hops_zero_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="max_hops"):
            c.trace_impact("TSMC_TI", max_hops=0)

    def test_max_hops_too_large_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="max_hops"):
            c.trace_impact("TSMC_TI", max_hops=6)

    def test_max_hops_non_int_raises(self):
        c = GraphClient()
        with pytest.raises(ValueError, match="max_hops"):
            c.trace_impact("TSMC_TI", max_hops=2.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTraceImpactReturnType:

    def test_returns_list(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        assert isinstance(result, list)

    def test_each_element_is_dict(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        for item in result:
            assert isinstance(item, dict)

    def test_each_dict_has_required_keys(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        for item in result:
            assert set(item.keys()) == {"ticker", "name", "sector"}

    def test_all_values_are_strings(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        for item in result:
            assert isinstance(item["ticker"], str)
            assert isinstance(item["name"], str)
            assert isinstance(item["sector"], str)


# ---------------------------------------------------------------------------
# TSMC shock — correctness of propagation
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.usefixtures("seed_graph")
class TestTraceTsmcShock:

    def test_no_impact_on_unknown_ticker(self, client: GraphClient):
        result = client.trace_impact("UNKNOWN_TICKER_XYZ", max_hops=3)
        assert result == []

    def test_tsmc_shock_1hop_finds_direct_dependents(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        tickers = {r["ticker"] for r in result}
        assert _AAPL in tickers, f"AAPL_TI missing from 1-hop result: {tickers}"
        assert _NVDA in tickers, f"NVDA_TI missing from 1-hop result: {tickers}"

    def test_tsmc_shock_1hop_excludes_indirect(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        tickers = {r["ticker"] for r in result}
        assert _DELL not in tickers, f"DELL_TI should be absent from 1-hop result"

    def test_tsmc_shock_2hop_finds_indirect_dependent(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=2)
        tickers = {r["ticker"] for r in result}
        assert _DELL in tickers, f"DELL_TI missing from 2-hop result: {tickers}"

    def test_tsmc_shock_1hop_count(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        assert len(result) == 2

    def test_tsmc_shock_2hop_count(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=2)
        assert len(result) == 3

    def test_result_tickers_are_deduplicated(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=3)
        tickers = [r["ticker"] for r in result]
        assert len(tickers) == len(set(tickers)), f"Duplicate tickers: {tickers}"

    def test_company_names_populated(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=2)
        for item in result:
            assert item["name"], f"Empty name for ticker {item['ticker']!r}"

    def test_max_hops_boundary_one_accepted(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=1)
        assert isinstance(result, list)

    def test_max_hops_boundary_five_accepted(self, client: GraphClient):
        result = client.trace_impact(_TSMC, max_hops=5)
        assert isinstance(result, list)

"""
Tests for Phase 1.3 — Causal Betas on Graph Edges.

Covers:
  - price_fetcher: yfinance wrapper
  - beta_calculator: OLS / Granger causal estimation
  - calibrator: end-to-end orchestration
  - trace_impact handler: causal fields in response
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic daily close price DataFrame."""
    rng = np.random.default_rng(seed)
    prices = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame({"Close": prices}, index=idx)


def _make_correlated_prices(
    upstream: pd.DataFrame,
    lag: int = 3,
    beta: float = 0.7,
    noise: float = 0.005,
    seed: int = 99,
) -> pd.DataFrame:
    """Generate a downstream price series correlated with upstream at given lag."""
    rng = np.random.default_rng(seed)
    upstream_ret = np.log(upstream["Close"] / upstream["Close"].shift(1)).dropna()
    n = len(upstream_ret)
    downstream_ret = pd.Series(0.0, index=upstream_ret.index)
    for i in range(lag, n):
        downstream_ret.iloc[i] = beta * upstream_ret.iloc[i - lag] + rng.normal(0, noise)
    # Rebuild prices from returns
    prices = 100.0 * np.exp(downstream_ret.cumsum())
    return pd.DataFrame({"Close": prices}, index=upstream_ret.index)


# ---------------------------------------------------------------------------
# TestPriceFetcher
# ---------------------------------------------------------------------------

class TestPriceFetcher:
    """Tests for finance_mcp.causal.price_fetcher"""

    def test_fetch_returns_dataframe_with_close_column(self):
        """Successful download returns a DataFrame with a 'Close' column."""
        from finance_mcp.causal.price_fetcher import fetch_price_history

        mock_df = _make_prices(100)
        with patch("finance_mcp.causal.price_fetcher.yf") as mock_yf:
            mock_yf.download.return_value = mock_df
            result = asyncio.get_event_loop().run_until_complete(
                fetch_price_history("AAPL")
            )

        assert isinstance(result, pd.DataFrame)
        assert "Close" in result.columns
        assert len(result) == 100

    def test_fetch_returns_empty_on_all_failures(self):
        """Empty yfinance result for every suffix returns empty DataFrame."""
        from finance_mcp.causal.price_fetcher import fetch_price_history

        with patch("finance_mcp.causal.price_fetcher.yf") as mock_yf:
            mock_yf.download.return_value = pd.DataFrame()
            result = asyncio.get_event_loop().run_until_complete(
                fetch_price_history("INVALID")
            )

        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_fetch_tries_exchange_suffixes(self):
        """Falls through empty results and succeeds on a later suffix."""
        from finance_mcp.causal.price_fetcher import fetch_price_history

        mock_df = _make_prices(50)
        call_count = 0

        def fake_download(ticker, **_):
            nonlocal call_count
            call_count += 1
            # Return real data only on the 3rd call (suffix ".BO")
            return mock_df if call_count >= 3 else pd.DataFrame()

        with patch("finance_mcp.causal.price_fetcher.yf") as mock_yf:
            mock_yf.download.side_effect = fake_download
            result = asyncio.get_event_loop().run_until_complete(
                fetch_price_history("RELIANCE")
            )

        assert not result.empty
        assert call_count == 3

    def test_fetch_handles_multiindex_columns(self):
        """MultiIndex columns (yfinance >= 0.2) are flattened correctly."""
        from finance_mcp.causal.price_fetcher import fetch_price_history

        # Build a DataFrame with MultiIndex columns
        close_vals = _make_prices(80)["Close"]
        midx = pd.MultiIndex.from_tuples([("Close", "AAPL")])
        multi_df = pd.DataFrame(close_vals.values, index=close_vals.index, columns=midx)

        with patch("finance_mcp.causal.price_fetcher.yf") as mock_yf:
            mock_yf.download.return_value = multi_df
            result = asyncio.get_event_loop().run_until_complete(
                fetch_price_history("AAPL")
            )

        assert "Close" in result.columns

    def test_fetch_exception_falls_through_to_empty(self):
        """An exception during download is caught and treated as no-data."""
        from finance_mcp.causal.price_fetcher import fetch_price_history

        with patch("finance_mcp.causal.price_fetcher.yf") as mock_yf:
            mock_yf.download.side_effect = RuntimeError("network error")
            result = asyncio.get_event_loop().run_until_complete(
                fetch_price_history("BROKEN")
            )

        assert result.empty


# ---------------------------------------------------------------------------
# TestComputeEdgeBeta
# ---------------------------------------------------------------------------

class TestComputeEdgeBeta:
    """Tests for finance_mcp.causal.beta_calculator.compute_edge_beta"""

    def test_returns_calibration_on_sufficient_data(self):
        """Returns EdgeCalibration when series are long enough."""
        from finance_mcp.causal.beta_calculator import compute_edge_beta, EdgeCalibration

        upstream = _make_prices(300)
        downstream = _make_correlated_prices(upstream, lag=3, beta=0.6)
        result = compute_edge_beta(upstream, downstream, max_lag=10)

        assert result is not None
        assert isinstance(result, EdgeCalibration)

    def test_returns_none_on_insufficient_data(self):
        """Returns None when fewer than max_lag + 30 common observations."""
        from finance_mcp.causal.beta_calculator import compute_edge_beta

        upstream = _make_prices(20)
        downstream = _make_correlated_prices(upstream, lag=1)
        result = compute_edge_beta(upstream, downstream, max_lag=30)

        assert result is None

    def test_beta_positive_for_positive_correlation(self):
        """Beta should be positive when upstream and downstream move together."""
        from finance_mcp.causal.beta_calculator import compute_edge_beta

        upstream = _make_prices(400)
        # Strong positive beta (0.8) with lag=2
        downstream = _make_correlated_prices(upstream, lag=2, beta=0.8, noise=0.001)
        result = compute_edge_beta(upstream, downstream, max_lag=10)

        assert result is not None
        assert result.beta > 0

    def test_r_squared_between_0_and_1(self):
        """R² must be in [0, 1]."""
        from finance_mcp.causal.beta_calculator import compute_edge_beta

        upstream = _make_prices(350)
        downstream = _make_correlated_prices(upstream, lag=1, beta=0.5)
        result = compute_edge_beta(upstream, downstream, max_lag=5)

        assert result is not None
        assert 0.0 <= result.r_squared <= 1.0

    def test_lag_days_within_range(self):
        """Selected lag_days must be in [1, max_lag]."""
        from finance_mcp.causal.beta_calculator import compute_edge_beta

        max_lag = 10
        upstream = _make_prices(350)
        downstream = _make_correlated_prices(upstream, lag=4, beta=0.6)
        result = compute_edge_beta(upstream, downstream, max_lag=max_lag)

        assert result is not None
        assert 1 <= result.lag_days <= max_lag

    def test_p_value_between_0_and_1(self):
        """Granger p-value must be in [0, 1]."""
        from finance_mcp.causal.beta_calculator import compute_edge_beta

        upstream = _make_prices(350)
        downstream = _make_correlated_prices(upstream, lag=2, beta=0.7, noise=0.001)
        result = compute_edge_beta(upstream, downstream, max_lag=5)

        assert result is not None
        assert 0.0 <= result.p_value <= 1.0

    def test_n_observations_populated(self):
        """n_observations reflects common index size."""
        from finance_mcp.causal.beta_calculator import compute_edge_beta

        n = 300
        upstream = _make_prices(n)
        downstream = _make_correlated_prices(upstream, lag=1, beta=0.5)
        result = compute_edge_beta(upstream, downstream, max_lag=5)

        assert result is not None
        # n_observations ≤ n (log returns remove one row; alignment removes lag rows)
        assert result.n_observations <= n
        assert result.n_observations > 0


# ---------------------------------------------------------------------------
# TestCalibrator
# ---------------------------------------------------------------------------

class TestCalibrator:
    """Tests for finance_mcp.causal.calibrator.calibrate_all_edges"""

    def _make_mock_client(self, edges=None):
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.get_all_depends_on_edges.return_value = edges or []
        client.update_edge_causal.return_value = True
        return client

    def test_empty_graph_returns_zero_counts(self):
        """No edges in graph produces a zeroed CalibrationResult."""
        from finance_mcp.causal.calibrator import calibrate_all_edges

        mock_client = self._make_mock_client(edges=[])
        with patch("finance_mcp.causal.calibrator.GraphClient", return_value=mock_client):
            result = asyncio.get_event_loop().run_until_complete(
                calibrate_all_edges()
            )

        assert result.edges_processed == 0
        assert result.edges_updated == 0
        assert result.edges_skipped == 0
        assert result.errors == []

    def test_skips_when_price_data_missing(self):
        """Edges are skipped when price data unavailable for a ticker."""
        from finance_mcp.causal.calibrator import calibrate_all_edges

        edges = [{"src": "AAPL", "dst": "TSMC", "weight": 0.9}]
        mock_client = self._make_mock_client(edges=edges)

        with patch("finance_mcp.causal.calibrator.GraphClient", return_value=mock_client):
            with patch("finance_mcp.causal.calibrator.fetch_price_history", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = pd.DataFrame()  # no data
                result = asyncio.get_event_loop().run_until_complete(
                    calibrate_all_edges()
                )

        assert result.edges_processed == 1
        assert result.edges_skipped == 1
        assert result.edges_updated == 0

    def test_updates_edges_with_calibration(self):
        """update_edge_causal is called for each successfully calibrated edge."""
        from finance_mcp.causal.calibrator import calibrate_all_edges
        from finance_mcp.causal.beta_calculator import EdgeCalibration

        upstream_df = _make_prices(350)
        downstream_df = _make_correlated_prices(upstream_df, lag=3, beta=0.6)

        edges = [{"src": "NVDA", "dst": "TSMC", "weight": 0.9}]
        mock_client = self._make_mock_client(edges=edges)

        async def fake_fetch(ticker, years=2):
            if ticker == "TSMC":
                return upstream_df
            return downstream_df

        fake_calibration = EdgeCalibration(
            beta=0.6, lag_days=3, r_squared=0.45, p_value=0.02, n_observations=340,
        )

        with patch("finance_mcp.causal.calibrator.GraphClient", return_value=mock_client):
            with patch("finance_mcp.causal.calibrator.fetch_price_history", side_effect=fake_fetch):
                with patch("finance_mcp.causal.calibrator.compute_edge_beta", return_value=fake_calibration):
                    result = asyncio.get_event_loop().run_until_complete(
                        calibrate_all_edges()
                    )

        assert result.edges_updated == 1
        assert result.edges_skipped == 0
        mock_client.update_edge_causal.assert_called_once_with(
            src_ticker="NVDA",
            dst_ticker="TSMC",
            beta=0.6,
            lag_days=3,
            r_squared=0.45,
        )

    def test_insufficient_data_counts_as_skipped(self):
        """None returned by compute_edge_beta increments edges_skipped."""
        from finance_mcp.causal.calibrator import calibrate_all_edges

        upstream_df = _make_prices(350)
        downstream_df = _make_correlated_prices(upstream_df, lag=2)
        edges = [{"src": "AMD", "dst": "TSMC", "weight": 0.8}]
        mock_client = self._make_mock_client(edges=edges)

        async def fake_fetch(ticker, years=2):
            return upstream_df if ticker == "TSMC" else downstream_df

        with patch("finance_mcp.causal.calibrator.GraphClient", return_value=mock_client):
            with patch("finance_mcp.causal.calibrator.fetch_price_history", side_effect=fake_fetch):
                with patch("finance_mcp.causal.calibrator.compute_edge_beta", return_value=None):
                    result = asyncio.get_event_loop().run_until_complete(
                        calibrate_all_edges()
                    )

        assert result.edges_skipped == 1
        assert result.edges_updated == 0
        mock_client.update_edge_causal.assert_not_called()

    def test_price_fetch_error_recorded_in_errors(self):
        """Exception from fetch_price_history is captured in result.errors."""
        from finance_mcp.causal.calibrator import calibrate_all_edges

        edges = [{"src": "AAPL", "dst": "TSMC", "weight": 0.9}]
        mock_client = self._make_mock_client(edges=edges)

        async def broken_fetch(ticker, years=2):
            raise RuntimeError("yfinance down")

        with patch("finance_mcp.causal.calibrator.GraphClient", return_value=mock_client):
            with patch("finance_mcp.causal.calibrator.fetch_price_history", side_effect=broken_fetch):
                result = asyncio.get_event_loop().run_until_complete(
                    calibrate_all_edges()
                )

        assert len(result.errors) > 0
        assert "yfinance down" in result.errors[0]

    def test_as_dict_has_expected_keys(self):
        """CalibrationResult.as_dict() returns all required keys."""
        from finance_mcp.causal.calibrator import CalibrationResult

        cr = CalibrationResult(
            edges_processed=5,
            edges_updated=3,
            edges_skipped=2,
            errors=["oops"],
        )
        d = cr.as_dict()
        assert set(d.keys()) == {"edges_processed", "edges_updated", "edges_skipped", "errors"}
        assert d["edges_processed"] == 5
        assert d["errors"] == ["oops"]


# ---------------------------------------------------------------------------
# TestGraphClientCausal
# ---------------------------------------------------------------------------

class TestGraphClientCausal:
    """Tests for new GraphClient causal methods."""

    def _make_driver(self, run_results=None):
        """Return a mock neo4j driver that yields run_results from session.run."""
        driver = MagicMock()
        session = MagicMock()
        result_mock = MagicMock()
        result_mock.__iter__ = MagicMock(
            return_value=iter([MagicMock(**{"__iter__": MagicMock(return_value=iter([])), "data": MagicMock(return_value=r)}) for r in (run_results or [])])
        )
        session.run.return_value = run_results or []
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        return driver, session

    @patch("finance_mcp.graph.client.GraphDatabase")
    def test_get_all_depends_on_edges_calls_correct_query(self, mock_gdb):
        from finance_mcp.graph.client import GraphClient

        driver = MagicMock()
        session = MagicMock()
        session.run.return_value = iter([])
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gdb.driver.return_value = driver

        with GraphClient() as client:
            client.get_all_depends_on_edges()

        call_args = session.run.call_args[0][0]
        assert "DEPENDS_ON" in call_args
        assert "src" in call_args or "a.ticker" in call_args

    @patch("finance_mcp.graph.client.GraphDatabase")
    def test_update_edge_causal_calls_set_query(self, mock_gdb):
        from finance_mcp.graph.client import GraphClient

        driver = MagicMock()
        session = MagicMock()
        session.run.return_value = iter([])
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        mock_gdb.driver.return_value = driver

        with GraphClient() as client:
            client.update_edge_causal("NVDA", "TSMC", beta=0.5, lag_days=3, r_squared=0.4)

        call_args = session.run.call_args[0][0]
        assert "SET" in call_args
        assert "beta" in call_args
        assert "lag_days" in call_args
        assert "r_squared" in call_args

    @patch("finance_mcp.graph.client.GraphDatabase")
    def test_update_edge_causal_validates_vid(self, mock_gdb):
        from finance_mcp.graph.client import GraphClient

        mock_gdb.driver.return_value = MagicMock()

        with GraphClient() as client:
            with pytest.raises(ValueError):
                client.update_edge_causal("NVDA!!!", "TSMC", beta=0.5, lag_days=3, r_squared=0.4)


# ---------------------------------------------------------------------------
# TestTraceImpactWithCausalFields
# ---------------------------------------------------------------------------

class TestTraceImpactWithCausalFields:
    """Verify trace_impact handler passes causal fields through to the response."""

    @pytest.mark.asyncio
    async def test_response_includes_causal_fields(self):
        """ToolResponse.data.impacted_companies contains beta/lag_days/r_squared."""
        from mcp_server.invoke_handlers.trace_impact import handle_trace_impact

        mock_impacted = [
            {
                "ticker": "NVDA",
                "name": "NVIDIA",
                "sector": "Technology",
                "beta": 0.73,
                "lag_days": 4,
                "r_squared": 0.81,
            }
        ]

        with patch("mcp_server.invoke_handlers.trace_impact.GraphClient") as MockGC:
            instance = MagicMock()
            instance.__enter__ = MagicMock(return_value=instance)
            instance.__exit__ = MagicMock(return_value=False)
            instance.trace_impact.return_value = mock_impacted
            MockGC.return_value = instance

            response = await handle_trace_impact("TSMC", max_hops=2)

        assert response.success is True
        companies = response.data["impacted_companies"]
        assert len(companies) == 1
        assert companies[0]["beta"] == 0.73
        assert companies[0]["lag_days"] == 4
        assert companies[0]["r_squared"] == 0.81

    @pytest.mark.asyncio
    async def test_causal_fields_are_none_before_calibration(self):
        """Before calibration, beta/lag_days/r_squared are None (not missing keys)."""
        from mcp_server.invoke_handlers.trace_impact import handle_trace_impact

        mock_impacted = [
            {
                "ticker": "NVDA",
                "name": "NVIDIA",
                "sector": "Technology",
                "beta": None,
                "lag_days": None,
                "r_squared": None,
            }
        ]

        with patch("mcp_server.invoke_handlers.trace_impact.GraphClient") as MockGC:
            instance = MagicMock()
            instance.__enter__ = MagicMock(return_value=instance)
            instance.__exit__ = MagicMock(return_value=False)
            instance.trace_impact.return_value = mock_impacted
            MockGC.return_value = instance

            response = await handle_trace_impact("TSMC", max_hops=1)

        assert response.success is True
        company = response.data["impacted_companies"][0]
        # Keys must exist even if None
        assert "beta" in company
        assert "lag_days" in company
        assert "r_squared" in company
        assert company["beta"] is None


# ---------------------------------------------------------------------------
# TestCalibrateEdgesEndpoint
# ---------------------------------------------------------------------------

class TestCalibrateEdgesEndpoint:
    """Tests for POST /calibrate/edges endpoint."""

    def test_calibrate_edges_returns_started(self):
        """Endpoint returns 200 with status=started immediately."""
        from fastapi.testclient import TestClient
        from mcp_server.server import app

        with TestClient(app, headers={"X-API-Key": "dev_key_change_in_production"}) as client:
            with patch("mcp_server.server._run_edge_calibration"):
                response = client.post("/calibrate/edges")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "message" in data

    def test_calibrate_edges_requires_api_key(self):
        """Endpoint rejects requests without X-API-Key header."""
        from fastapi.testclient import TestClient
        from mcp_server.server import app

        with TestClient(app) as client:
            response = client.post("/calibrate/edges")

        assert response.status_code == 401

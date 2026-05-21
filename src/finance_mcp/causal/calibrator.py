"""
finance_mcp.causal.calibrator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Orchestrates full-graph causal beta calibration.

Fetches every DEPENDS_ON edge from Memgraph, downloads 2 years of daily
close prices via yfinance (deduplicating ticker fetches), computes OLS
betas at the optimal lag, and writes beta / lag_days / r_squared back to
the graph.

Public API
----------
async def calibrate_all_edges(host, port) -> CalibrationResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from finance_mcp.graph.client import GraphClient, DEFAULT_HOST, DEFAULT_PORT
from finance_mcp.causal.price_fetcher import fetch_price_history
from finance_mcp.causal.beta_calculator import compute_edge_beta

logger = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    edges_processed: int = 0
    edges_updated: int = 0
    edges_skipped: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "edges_processed": self.edges_processed,
            "edges_updated": self.edges_updated,
            "edges_skipped": self.edges_skipped,
            "errors": self.errors,
        }


async def calibrate_all_edges(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> CalibrationResult:
    """
    Calibrate causal betas for all DEPENDS_ON edges in the graph.

    Edge semantics:
        (src)-[:DEPENDS_ON]->(dst)
        dst is the upstream supplier; src is the downstream dependent.

    For each edge: beta measures how much src's return changes when dst's
    return shifts by 1 unit, with a lag of lag_days trading days.
    """
    result = CalibrationResult()

    with GraphClient(host=host, port=port) as client:
        edges = client.get_all_depends_on_edges()

    if not edges:
        logger.info("calibrate_all_edges: no DEPENDS_ON edges found")
        return result

    # Collect unique tickers to minimise yfinance round-trips
    tickers: set[str] = set()
    for edge in edges:
        tickers.add(edge["src"])
        tickers.add(edge["dst"])

    price_cache: Dict[str, object] = {}
    for ticker in sorted(tickers):
        try:
            df = await fetch_price_history(ticker)
            if not df.empty:
                price_cache[ticker] = df
            else:
                logger.warning("calibrate: no price data for %s", ticker)
        except Exception as exc:
            result.errors.append(f"price_fetch {ticker}: {exc}")

    logger.info(
        "calibrate_all_edges: %d edges, %d/%d tickers with price data",
        len(edges), len(price_cache), len(tickers),
    )

    with GraphClient(host=host, port=port) as client:
        for edge in edges:
            src = edge["src"]
            dst = edge["dst"]
            result.edges_processed += 1

            if src not in price_cache or dst not in price_cache:
                result.edges_skipped += 1
                continue

            try:
                # dst is upstream (supplier), src is downstream (dependent)
                calibration = compute_edge_beta(
                    upstream_prices=price_cache[dst],
                    downstream_prices=price_cache[src],
                )
                if calibration is None:
                    logger.debug("calibrate: insufficient data for %s->%s", src, dst)
                    result.edges_skipped += 1
                    continue

                client.update_edge_causal(
                    src_ticker=src,
                    dst_ticker=dst,
                    beta=calibration.beta,
                    lag_days=calibration.lag_days,
                    r_squared=calibration.r_squared,
                )
                result.edges_updated += 1
                logger.info(
                    "calibrate: %s->%s beta=%.4f lag=%d r2=%.4f p=%.4f",
                    src, dst,
                    calibration.beta, calibration.lag_days,
                    calibration.r_squared, calibration.p_value,
                )

            except Exception as exc:
                result.errors.append(f"calibrate {src}->{dst}: {exc}")
                result.edges_skipped += 1

    return result

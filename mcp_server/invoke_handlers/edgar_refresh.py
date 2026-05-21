"""
edgar_refresh Tool Handler
MCP tool: edgar_refresh

Fetches the most recent 10-K from SEC EDGAR for a given ticker, uses GPT-4o
to extract named supplier/customer relationships, and writes them to Memgraph
as DEPENDS_ON edges tagged with source='EDGAR'.

Security
--------
* ticker is validated against the same VID regex used by GraphClient.
* EDGAR URLs are built from structured fields (CIK, accession no.), not from
  user input — no SSRF surface.
* GPT-4o output is parsed as JSON with strict field validation before writing
  to the graph.
"""
from __future__ import annotations

import re
import time
from typing import Optional

from mcp_server.config import get_settings
from mcp_server.schemas import ToolResponse
from mcp_server.utils.logging import get_logger
from finance_mcp.edgar.edgar_client import fetch_10k_filing, EdgarError
from finance_mcp.edgar.supplier_extractor import extract_supplier_relationships
from finance_mcp.edgar.graph_updater import update_graph_from_filing

logger = get_logger(__name__)

_TICKER_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')


async def handle_edgar_refresh(
    ticker: str,
    agent_id: Optional[str] = None,
) -> ToolResponse:
    """
    Refresh the supply chain graph with 10-K data from SEC EDGAR.

    Flow
    ----
    1. Validate ticker format.
    2. Resolve ticker → CIK via EDGAR company tickers index.
    3. Fetch most recent 10-K primary document (Business + Risk Factors).
    4. Extract supplier/customer relationships via GPT-4o.
    5. Write relationships to Memgraph as DEPENDS_ON edges.

    Parameters
    ----------
    ticker   : str        — SEC-registered stock ticker, e.g. "AAPL", "NVDA".
    agent_id : str | None — optional caller identifier for logging.

    Returns
    -------
    ToolResponse
        success=True:
            data = {
                "ticker":               str,
                "filing_date":          str,   ISO-8601
                "relationships_found":  int,
                "new_edges_added":      int,
                "updated_edges":        int,
                "companies_discovered": int,
                "errors":               [str],
            }
        success=False: descriptive error string.
    """
    start_time = time.time()
    settings = get_settings()

    # ------------------------------------------------------------------
    # Validate ticker
    # ------------------------------------------------------------------
    if not isinstance(ticker, str) or not ticker.strip():
        return ToolResponse(success=False, error="'ticker' must be a non-empty string.")

    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        return ToolResponse(
            success=False,
            error=(
                f"Invalid ticker format: {ticker!r}. "
                "Allowed characters: A–Z, 0–9, underscore, dot, hyphen. Max 64 characters."
            ),
        )

    logger.info("edgar_refresh_request", ticker=ticker, agent_id=agent_id)

    # ------------------------------------------------------------------
    # Stage 1 — Fetch 10-K from EDGAR
    # ------------------------------------------------------------------
    try:
        filing_text, filing_date = await fetch_10k_filing(ticker)
    except EdgarError as exc:
        return ToolResponse(success=False, error=str(exc))
    except Exception as exc:
        logger.error("edgar_refresh_fetch_error", ticker=ticker, error=str(exc))
        return ToolResponse(success=False, error=f"EDGAR fetch failed: {exc}")

    # ------------------------------------------------------------------
    # Stage 2 — Extract relationships via GPT-4o
    # ------------------------------------------------------------------
    relationships = await extract_supplier_relationships(filing_text, ticker)

    if not relationships:
        return ToolResponse(
            success=True,
            data={
                "ticker": ticker,
                "filing_date": filing_date,
                "relationships_found": 0,
                "new_edges_added": 0,
                "updated_edges": 0,
                "companies_discovered": 0,
                "errors": [],
                "note": (
                    "10-K fetched successfully but no named supplier/customer "
                    "relationships were found in the Business or Risk Factors sections."
                ),
            },
            latency_ms=(time.time() - start_time) * 1000,
        )

    # ------------------------------------------------------------------
    # Stage 3 — Write to Memgraph
    # ------------------------------------------------------------------
    try:
        update_result = await update_graph_from_filing(
            ticker=ticker,
            relationships=relationships,
            filing_date=filing_date,
            host=settings.memgraph_host,
            port=settings.memgraph_port,
        )
    except Exception as exc:
        logger.error("edgar_refresh_graph_error", ticker=ticker, error=str(exc))
        return ToolResponse(success=False, error=f"Graph update failed: {exc}")

    latency_ms = (time.time() - start_time) * 1000
    logger.info(
        "edgar_refresh_complete ticker=%s filing=%s new=%d updated=%d discovered=%d latency=%.0fms",
        ticker,
        filing_date,
        update_result.new_edges_added,
        update_result.updated_edges,
        update_result.companies_discovered,
        latency_ms,
    )

    return ToolResponse(
        success=True,
        data={
            "ticker": ticker,
            "filing_date": filing_date,
            "relationships_found": len(relationships),
            "new_edges_added": update_result.new_edges_added,
            "updated_edges": update_result.updated_edges,
            "companies_discovered": update_result.companies_discovered,
            "errors": update_result.errors,
        },
        latency_ms=latency_ms,
    )

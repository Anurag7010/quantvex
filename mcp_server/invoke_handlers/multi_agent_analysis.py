"""
Multi-Agent Analysis Tool Handler
MCP tool: multi_agent_analysis
"""

from __future__ import annotations

import time
from typing import Optional

from finance_mcp.reasoning.orchestrator import run_multi_agent_analysis
from mcp_server.schemas import ToolResponse
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)


async def handle_multi_agent_analysis(
    query: str,
    ticker: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> ToolResponse:
    """Run additive bull/bear/judge reasoning and return a structured verdict."""
    start_time = time.time()

    if not isinstance(query, str) or not query.strip():
        return ToolResponse(success=False, error="'query' must be a non-empty string.")

    query = query.strip()
    ticker = (ticker or "").strip().upper() or None

    logger.info(
        "multi_agent_analysis_request",
        query=query,
        ticker=ticker,
        agent_id=agent_id,
    )

    try:
        result = await run_multi_agent_analysis(query=query, ticker=ticker)
        latency_ms = (time.time() - start_time) * 1000
        return ToolResponse(
            success=True,
            data=result,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("multi_agent_analysis_error", error=str(exc))
        latency_ms = (time.time() - start_time) * 1000
        return ToolResponse(
            success=False,
            error=f"Multi-agent analysis failed: {exc}",
            latency_ms=latency_ms,
        )

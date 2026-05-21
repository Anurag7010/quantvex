"""
Multi-Agent Analysis Tool Handler
MCP tool: multi_agent_analysis
"""

from __future__ import annotations

import re
import time
from typing import Optional

from finance_mcp.reasoning.orchestrator import run_multi_agent_analysis
from mcp_server.schemas import ToolResponse
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

_PRICE_RE = re.compile(r"quote is ([\d.]+)")


def _extract_price_from_result(result: dict) -> Optional[float]:
    """Parse the live price from bull-case signals (set during quote.latest call)."""
    for signal in result.get("bull_case", {}).get("signals", []):
        m = _PRICE_RE.search(signal)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


async def handle_multi_agent_analysis(
    query: str,
    ticker: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> ToolResponse:
    """Run adversarial bull/bear/judge reasoning and return a structured verdict."""
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

        # Record verdict for accuracy tracking (fire-and-forget; never fails the response)
        try:
            from finance_mcp.verdict_history.tracker import record_verdict
            from mcp_server.config import get_settings
            await record_verdict(
                {
                    "ticker": ticker or result.get("ticker"),
                    "query": query,
                    "verdict": result.get("verdict"),
                    "confidence": result.get("confidence"),
                    "price_at_verdict": _extract_price_from_result(result),
                },
                db_path=get_settings().verdict_db_path,
            )
        except Exception as exc:
            logger.warning("verdict_record_failed", error=str(exc))

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

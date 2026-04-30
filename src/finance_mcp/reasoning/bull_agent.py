from __future__ import annotations

import logging
from typing import List

from finance_mcp.reasoning.schemas import AgentInput, AgentOutput
from finance_mcp.services import get_quote, run_news_pipeline, trace_impact

logger = logging.getLogger(__name__)

_NEWS_KEYWORDS = (
    "war",
    "conflict",
    "sanction",
    "disruption",
    "shutdown",
    "shortage",
    "crisis",
    "hike",
    "geopolitical",
)


def _should_run_news(query: str) -> bool:
    query_l = query.lower()
    return any(keyword in query_l for keyword in _NEWS_KEYWORDS)


async def run_bull_agent(agent_input: AgentInput) -> AgentOutput:
    """Build a constructive (upside) case from MCP tool evidence."""
    ticker = (agent_input.ticker or "").strip().upper() or None

    signals: List[str] = []
    confidence = 0.35

    if ticker:
        try:
            quote_res = await get_quote(ticker)
            if quote_res["success"] and quote_res.get("data"):
                data = quote_res["data"]
                price = data.get("price")
                source = data.get("data_source", "unknown")
                cache_hit = data.get("cache_hit", False)
                signals.append(
                    f"Latest {ticker} quote is {price} (source: {source}, cache={cache_hit})."
                )
                confidence += 0.12
        except Exception as exc:  # noqa: BLE001
            logger.warning("bull_agent quote.latest failed: %s", exc)

        try:
            impact_res = await trace_impact(ticker, hops=2)
            if impact_res["success"] and impact_res.get("data"):
                impacted = impact_res["data"].get("impacted_count", 0)
                if impacted > 0:
                    signals.append(
                        f"Graph shows {impacted} downstream dependents, indicating strategic supply importance."
                    )
                    confidence += 0.12
        except Exception as exc:  # noqa: BLE001
            logger.warning("bull_agent trace_impact failed: %s", exc)

    if _should_run_news(agent_input.query):
        try:
            news_res = await run_news_pipeline(
                query=agent_input.query,
                ticker=ticker,
                limit=5,
                max_hops=2,
            )
            if news_res["success"] and news_res.get("data"):
                events_found = news_res["data"].get("events_found", 0)
                cascade = news_res["data"].get("total_cascade_companies", 0)
                if events_found > 0:
                    signals.append(
                        f"Detected {events_found} disruption signals that can re-price leaders and substitute winners."
                    )
                    confidence += 0.08
                if cascade > 0:
                    signals.append(
                        f"Cascade touches {cascade} companies, creating selective upside for advantaged firms."
                    )
                    confidence += 0.06
        except Exception as exc:  # noqa: BLE001
            logger.warning("bull_agent analyze_news_impact failed: %s", exc)

    if not signals:
        signals.append("Limited hard signals available; upside case is currently weakly supported.")

    reasoning = (
        "Bull thesis focuses on potential pricing power, demand rotation, and supplier advantage. "
        + " ".join(signals)
    )

    return AgentOutput(
        stance="bull",
        reasoning=reasoning,
        signals=signals,
        confidence=max(0.0, min(confidence, 0.95)),
    )

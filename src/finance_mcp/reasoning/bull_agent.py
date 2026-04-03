from __future__ import annotations

import logging
from typing import List

from mcp_server.invoke_handlers.news_analysis import handle_news_analysis
from mcp_server.invoke_handlers.quote_latest import handle_quote_latest
from mcp_server.invoke_handlers.trace_impact import handle_trace_impact

from finance_mcp.reasoning.schemas import AgentInput, AgentOutput

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
            quote_res = await handle_quote_latest(
                symbol=ticker,
                max_age_sec=60,
                agent_id="bull_agent",
                query_text=agent_input.query,
            )
            if quote_res.success and quote_res.data:
                price = quote_res.data.get("price")
                source = quote_res.data.get("data_source", "unknown")
                cache_hit = quote_res.data.get("cache_hit", False)
                signals.append(
                    f"Latest {ticker} quote is {price} (source: {source}, cache={cache_hit})."
                )
                confidence += 0.12
        except Exception as exc:  # noqa: BLE001
            logger.warning("bull_agent quote.latest failed: %s", exc)

        try:
            impact_res = await handle_trace_impact(
                ticker=ticker,
                max_hops=2,
                agent_id="bull_agent",
            )
            if impact_res.success and impact_res.data:
                impacted = impact_res.data.get("impacted_count", 0)
                if impacted > 0:
                    signals.append(
                        f"Graph shows {impacted} downstream dependents, indicating strategic supply importance."
                    )
                    confidence += 0.12
        except Exception as exc:  # noqa: BLE001
            logger.warning("bull_agent trace_impact failed: %s", exc)

    if _should_run_news(agent_input.query):
        try:
            news_res = await handle_news_analysis(
                query=agent_input.query,
                ticker=ticker,
                limit=5,
                max_hops=2,
                agent_id="bull_agent",
            )
            if news_res.success and news_res.data:
                events_found = news_res.data.get("events_found", 0)
                cascade = news_res.data.get("total_cascade_companies", 0)
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

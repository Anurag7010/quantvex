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
    "inflation",
    "geopolitical",
)


def _should_run_news(query: str) -> bool:
    query_l = query.lower()
    return any(keyword in query_l for keyword in _NEWS_KEYWORDS)


async def run_bear_agent(agent_input: AgentInput) -> AgentOutput:
    """Build a risk-first (downside) case from MCP tool evidence."""
    ticker = (agent_input.ticker or "").strip().upper() or None

    signals: List[str] = []
    confidence = 0.4

    if ticker:
        try:
            impact_res = await trace_impact(ticker, hops=3)
            if impact_res["success"] and impact_res.get("data"):
                impacted = impact_res["data"].get("impacted_count", 0)
                if impacted > 0:
                    signals.append(
                        f"Supply-chain graph shows {impacted} downstream dependencies, increasing disruption blast radius."
                    )
                    confidence += 0.15
        except Exception as exc:  # noqa: BLE001
            logger.warning("bear_agent trace_impact failed: %s", exc)

        try:
            quote_res = await get_quote(ticker)
            if quote_res["success"] and quote_res.get("data"):
                source = quote_res["data"].get("data_source", "unknown")
                signals.append(
                    f"Market quote monitoring active for {ticker} (source: {source}); valuation can re-rate rapidly under stress."
                )
                confidence += 0.06
        except Exception as exc:  # noqa: BLE001
            logger.warning("bear_agent quote.latest failed: %s", exc)

    if _should_run_news(agent_input.query):
        try:
            news_res = await run_news_pipeline(
                query=agent_input.query,
                ticker=ticker,
                limit=8,
                max_hops=3,
            )
            if news_res["success"] and news_res.get("data"):
                events_found = news_res["data"].get("events_found", 0)
                cascade = news_res["data"].get("total_cascade_companies", 0)
                if events_found > 0:
                    signals.append(
                        f"News parser flagged {events_found} disruption events (geopolitical/cost/supply risk)."
                    )
                    confidence += 0.12
                if cascade > 0:
                    signals.append(
                        f"Downstream cascade reaches {cascade} companies, implying broad second-order risk transmission."
                    )
                    confidence += 0.1
        except Exception as exc:  # noqa: BLE001
            logger.warning("bear_agent analyze_news_impact failed: %s", exc)

    if not signals:
        signals.append("Risk evidence is currently limited; bear case has lower conviction.")

    reasoning = (
        "Bear thesis emphasizes disruption propagation, margin pressure, and macro-volatility transmission. "
        + " ".join(signals)
    )

    return AgentOutput(
        stance="bear",
        reasoning=reasoning,
        signals=signals,
        confidence=max(0.0, min(confidence, 0.97)),
    )

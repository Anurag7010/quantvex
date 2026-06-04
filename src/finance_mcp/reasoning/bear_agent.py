from __future__ import annotations

import logging
from typing import List, Optional

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
    "risk",
    "supply",
    "chain",
    "tariff",
    "recession",
)

# Words that signal the user is asking from a bearish/skeptical framing.
# Symmetric counterpart lives in bull_agent._BULL_QUERY_WORDS.
_BEAR_QUERY_WORDS = frozenset(
    {"sell", "short", "bearish", "avoid", "decline", "distress",
     "collapse", "cliff", "delays", "loss", "risk of", "worried"}
)


def _should_run_news(query: str) -> bool:
    query_l = query.lower()
    return any(keyword in query_l for keyword in _NEWS_KEYWORDS)


def _query_bear_prior(query: str) -> float:
    """Return a confidence boost (0–0.20) when the query is framed bearishly.

    Symmetric with bull_agent._query_bull_prior.  Neither agent can earn more
    than +0.20 from framing alone, keeping the prior from overwhelming real signals.
    """
    q = query.lower()
    bear_hits = sum(1 for w in _BEAR_QUERY_WORDS if w in q)
    # Bull framing in a bear query context is a net negative for bear confidence.
    from finance_mcp.reasoning.bull_agent import _BULL_QUERY_WORDS  # avoid circular at module level
    bull_hits = sum(1 for w in _BULL_QUERY_WORDS if w in q)
    net = max(0, bear_hits - bull_hits)
    return min(net * 0.10, 0.20)


async def run_bear_agent(
    agent_input: AgentInput,
    bull_thesis: Optional[AgentOutput] = None,
) -> AgentOutput:
    """Build a risk-first (downside) case from MCP tool evidence.

    Confidence accumulation is intentionally symmetric with bull_agent so that
    the verdict reflects evidence quality, not structural bias.

    When ``bull_thesis`` is provided, the bear targets the bull's weakest claim
    in its narrative — but this does NOT add free confidence; the bear must earn
    signal-backed confidence the same way the bull does.
    """
    ticker = (agent_input.ticker or "").strip().upper() or None

    # --- Base confidence ---
    # Same starting point as bull (0.35).  Prior from query framing replaces the
    # old unconditional +0.08 attack-target bonus.
    confidence = 0.35 + _query_bear_prior(agent_input.query)

    signals: List[str] = []

    # Extract the specific claim to attack (narrative only — no free confidence).
    attack_target: Optional[str] = None
    if bull_thesis is not None:
        attack_target = bull_thesis.metadata.get("weakest_claim")

    if attack_target:
        signals.append(
            f"Challenging bull's weakest claim: '{attack_target}'. "
            "This requires confirmation from volume, macro, or credit signals."
        )
        # No confidence bonus here — the attack is narrative, not evidence.

    if ticker:
        try:
            impact_res = await trace_impact(ticker, hops=3)
            if impact_res["success"] and impact_res.get("data"):
                impacted = impact_res["data"].get("impacted_count", 0)
                if impacted > 0:
                    signals.append(
                        f"Supply-chain graph shows {impacted} downstream dependencies, "
                        "increasing disruption blast radius under an adverse scenario."
                    )
                    # Same weight as bull_agent (+0.12) — symmetric signal, different framing.
                    confidence += 0.12
                # Absence of dependents is NOT a bear signal — it just means limited graph coverage.
        except Exception as exc:  # noqa: BLE001
            logger.warning("bear_agent trace_impact failed: %s", exc)
            signals.append(
                f"Supply chain graph unreachable ({type(exc).__name__}); "
                "worst-case dependency risk cannot be bounded."
            )

        # Quote gives bear the same data awareness as bull, weighted slightly less
        # (bull's quote signals strategic momentum; bear's signals valuation stress).
        try:
            quote_res = await get_quote(ticker)
            if quote_res["success"] and quote_res.get("data"):
                price = quote_res["data"].get("price")
                signals.append(
                    f"Live price for {ticker} is {price}; "
                    "current valuation is subject to re-rating under adverse conditions."
                )
                confidence += 0.07  # symmetric to bull's +0.08, slightly less to preserve bull edge on clear buys
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
                        f"News parser flagged {events_found} disruption events "
                        "(geopolitical/cost/supply risk)."
                    )
                    confidence += 0.12
                if cascade > 0:
                    signals.append(
                        f"Downstream cascade reaches {cascade} companies, "
                        "implying broad second-order risk transmission."
                    )
                    confidence += 0.10
        except Exception as exc:  # noqa: BLE001
            logger.warning("bear_agent analyze_news_impact failed: %s", exc)

    if not signals:
        signals.append("Risk evidence is currently limited; bear case has lower conviction.")

    label = f"Bear case for {ticker}" if ticker else "Bear case"
    reasoning = f"{label}: " + " ".join(signals)

    return AgentOutput(
        stance="bear",
        reasoning=reasoning,
        signals=signals,
        confidence=max(0.0, min(confidence, 0.95)),  # same cap as bull
        metadata={"attack_target": attack_target},
    )

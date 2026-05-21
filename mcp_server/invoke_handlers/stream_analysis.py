"""
Streaming analysis handler — yields SSE events as the adversarial debate progresses.
"""

from __future__ import annotations

import json
import re
from typing import AsyncIterator, Optional

from finance_mcp.reasoning.bull_agent import run_bull_agent
from finance_mcp.reasoning.bear_agent import run_bear_agent
from finance_mcp.reasoning.judge_agent import run_judge_agent
from finance_mcp.reasoning.schemas import AgentInput, AgentOutput
from finance_mcp.reasoning.orchestrator import _generate_rebuttal, _fallback_case, _extract_ticker
from finance_mcp.verdict_history.tracker import record_verdict
from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

_PRICE_RE = re.compile(r"quote is ([\d.]+)")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _extract_price(bull_case: AgentOutput) -> Optional[float]:
    for signal in bull_case.signals:
        m = _PRICE_RE.search(signal)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


async def run_streaming_analysis(
    ticker: str,
    query: str,
) -> AsyncIterator[str]:
    """Async generator yielding SSE-formatted strings for each reasoning step."""
    resolved_ticker = ticker.strip().upper() or _extract_ticker(query)
    agent_input = AgentInput(query=query, ticker=resolved_ticker)

    yield _sse({"step": "init", "message": f"Starting analysis for {resolved_ticker or 'unknown'}..."})

    # Quote fetch step
    yield _sse({"step": "quote_fetch", "message": "Fetching live quote...", "data": {"symbol": resolved_ticker}})

    # Graph trace step
    yield _sse({"step": "graph_trace", "message": "Tracing supply chain dependencies...", "data": {}})

    # News fetch step
    yield _sse({"step": "news_fetch", "message": "Fetching recent news...", "data": {}})

    # Bull thesis
    yield _sse({"step": "bull_thesis", "message": "Building bull thesis...", "data": {}})
    try:
        bull_case = await run_bull_agent(agent_input)
    except Exception as exc:
        logger.error("stream_bull_agent_failed", exc_info=exc)
        bull_case = _fallback_case("bull", exc)

    yield _sse({
        "step": "bull_thesis",
        "message": "Bull case forming...",
        "data": {
            "confidence": bull_case.confidence,
            "signals": bull_case.signals[:3],
            "weakest_claim": bull_case.metadata.get("weakest_claim"),
        },
    })

    # Bear attack
    attack_target = bull_case.metadata.get("weakest_claim", "core thesis")
    yield _sse({
        "step": "bear_attack",
        "message": "Bear agent attacking weakest claim...",
        "data": {"attack_target": attack_target},
    })
    try:
        bear_case = await run_bear_agent(agent_input, bull_thesis=bull_case)
    except Exception as exc:
        logger.error("stream_bear_agent_failed", exc_info=exc)
        bear_case = _fallback_case("bear", exc)

    # Bull rebuttal
    bull_rebuttal = _generate_rebuttal(bull_case, bear_case)
    confidence_delta = round(bull_case.confidence - bear_case.confidence, 3)
    yield _sse({
        "step": "rebuttal",
        "message": "Bull rebuttal...",
        "data": {"rebuttal": bull_rebuttal, "confidence_delta": confidence_delta},
    })

    # Judge
    yield _sse({"step": "judge", "message": "Judge evaluating full transcript...", "data": {}})
    judge = run_judge_agent(bull_case, bear_case, bull_rebuttal=bull_rebuttal)

    full_result = {
        "query": query,
        "ticker": resolved_ticker,
        "bull_case": {
            "reasoning": bull_case.reasoning,
            "signals": bull_case.signals,
            "confidence": bull_case.confidence,
            "weakest_claim": bull_case.metadata.get("weakest_claim"),
        },
        "bear_case": {
            "reasoning": bear_case.reasoning,
            "signals": bear_case.signals,
            "confidence": bear_case.confidence,
            "attack_target": bear_case.metadata.get("attack_target"),
        },
        "bull_rebuttal": bull_rebuttal,
        "judge_verdict": judge.model_dump(),
        "final_verdict": judge.verdict,
        "verdict": judge.verdict,
        "conviction": judge.conviction,
        "confidence": judge.composite_confidence / 100.0,
        "composite_confidence": judge.composite_confidence,
        "confidence_gap": judge.confidence_gap,
        "summary": judge.summary,
        "key_drivers": judge.key_drivers,
        "time_horizon": judge.time_horizon,
        "generated_at": judge.generated_at,
    }

    # Record verdict (fire-and-forget)
    try:
        await record_verdict(
            {
                "ticker": resolved_ticker,
                "query": query,
                "verdict": judge.verdict,
                "confidence": judge.composite_confidence / 100.0,
                "price_at_verdict": _extract_price(bull_case),
            },
            db_path=get_settings().verdict_db_path,
        )
    except Exception as exc:
        logger.warning("stream_verdict_record_failed", error=str(exc))

    yield _sse({"step": "verdict", "message": "Verdict ready", "data": full_result})
    yield _sse({"step": "done"})

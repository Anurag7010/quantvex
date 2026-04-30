from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict

from finance_mcp.reasoning.bear_agent import run_bear_agent
from finance_mcp.reasoning.bull_agent import run_bull_agent
from finance_mcp.reasoning.judge_agent import run_judge_agent
from finance_mcp.reasoning.schemas import AgentInput, AgentOutput

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:USDT)?\b")
_COMMON_WORDS = {
    "WHAT",
    "WILL",
    "HAPPEN",
    "IF",
    "THE",
    "AND",
    "WITH",
    "IMPACT",
    "ON",
    "IS",
    "TO",
    "OF",
    "DUE",
}


def _extract_ticker(query: str) -> str | None:
    for match in _TICKER_RE.findall(query.upper()):
        if match not in _COMMON_WORDS and len(match) > 1:
            return match
    return None


def _fallback_case(stance: str, error: Exception | str) -> AgentOutput:
    msg = str(error)
    return AgentOutput(
        stance=stance,
        reasoning=f"{stance.title()} agent unavailable; fallback mode active ({msg}).",
        signals=[f"{stance.title()} agent fallback triggered."],
        confidence=0.2,
    )


async def run_multi_agent_analysis(query: str, ticker: str | None = None) -> Dict[str, Any]:
    """Run bull/bear/judge pipeline and always return a safe structured result."""
    resolved_ticker = (ticker or "").strip().upper() or _extract_ticker(query)
    agent_input = AgentInput(query=query, ticker=resolved_ticker)

    bull_task = asyncio.create_task(run_bull_agent(agent_input))
    bear_task = asyncio.create_task(run_bear_agent(agent_input))

    bull_raw, bear_raw = await asyncio.gather(bull_task, bear_task, return_exceptions=True)

    if isinstance(bull_raw, Exception):
        logger.error("bull_agent_failed", exc_info=bull_raw)
        bull_case = _fallback_case("bull", bull_raw)
    else:
        bull_case = bull_raw

    if isinstance(bear_raw, Exception):
        logger.error("bear_agent_failed", exc_info=bear_raw)
        bear_case = _fallback_case("bear", bear_raw)
    else:
        bear_case = bear_raw

    judge = run_judge_agent(bull_case, bear_case)

    return {
        "query": query,
        "ticker": resolved_ticker,
        "bull_case": {
            "reasoning": bull_case.reasoning,
            "signals": bull_case.signals,
            "confidence": bull_case.confidence,
        },
        "bear_case": {
            "reasoning": bear_case.reasoning,
            "signals": bear_case.signals,
            "confidence": bear_case.confidence,
        },
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

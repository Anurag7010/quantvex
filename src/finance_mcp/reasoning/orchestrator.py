from __future__ import annotations

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


def _generate_rebuttal(bull_case: AgentOutput, bear_case: AgentOutput) -> str:
    """Generate a brief bull rebuttal to the bear's targeted attack (≤50 tokens)."""
    attack_target = bear_case.metadata.get("attack_target")
    if not attack_target:
        return "Bull thesis stands; no specific claim was targeted."
    if bull_case.confidence >= bear_case.confidence * 0.85:
        return (
            f"Bull maintains: the concern about '{attack_target}' "
            "is acknowledged but does not invalidate the core supply-chain thesis."
        )
    return (
        f"Bull concedes '{attack_target}' is less certain than stated. "
        "The thesis relies on the remaining supporting signals."
    )


async def run_multi_agent_analysis(query: str, ticker: str | None = None) -> Dict[str, Any]:
    """Run sequential adversarial debate (bull → bear attack → bull rebuttal → judge)."""
    resolved_ticker = (ticker or "").strip().upper() or _extract_ticker(query)
    agent_input = AgentInput(query=query, ticker=resolved_ticker)

    # Step 1: Bull builds thesis with weakest_claim in metadata
    try:
        bull_case = await run_bull_agent(agent_input)
    except Exception as exc:
        logger.error("bull_agent_failed", exc_info=exc)
        bull_case = _fallback_case("bull", exc)

    # Step 2: Bear attacks bull's weakest claim specifically
    try:
        bear_case = await run_bear_agent(agent_input, bull_thesis=bull_case)
    except Exception as exc:
        logger.error("bear_agent_failed", exc_info=exc)
        bear_case = _fallback_case("bear", exc)

    # Step 3: Bull rebuttal (brief; maintains or concedes weakest claim)
    bull_rebuttal = _generate_rebuttal(bull_case, bear_case)

    # Step 4: Judge evaluates full transcript
    judge = run_judge_agent(bull_case, bear_case, bull_rebuttal=bull_rebuttal)

    return {
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

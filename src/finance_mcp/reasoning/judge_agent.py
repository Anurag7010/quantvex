from __future__ import annotations

from finance_mcp.reasoning.schemas import AgentOutput, JudgeOutput


def run_judge_agent(bull_case: AgentOutput, bear_case: AgentOutput) -> JudgeOutput:
    """Synthesize bull/bear outputs into a balanced final verdict."""
    bull_conf = max(0.0, min(bull_case.confidence, 1.0))
    bear_conf = max(0.0, min(bear_case.confidence, 1.0))

    gap = abs(bull_conf - bear_conf)
    avg_conf = (bull_conf + bear_conf) / 2.0

    if gap < 0.08:
        verdict = "Balanced / mixed outlook"
    elif bull_conf > bear_conf:
        verdict = "Leaning bullish"
    else:
        verdict = "Leaning bearish"

    if gap > 0.25:
        verdict = f"Strong {verdict.lower()}"

    key_drivers = []
    key_drivers.extend(bull_case.signals[:2])
    key_drivers.extend(bear_case.signals[:2])

    summary = (
        f"Bull confidence={bull_conf:.2f}, Bear confidence={bear_conf:.2f}. "
        "Decision combines upside catalysts and downside transmission risks from MCP tool evidence."
    )

    # Penalize final confidence when both sides are close (high uncertainty)
    final_confidence = max(0.2, min(0.98, avg_conf - (0.1 if gap < 0.08 else 0.0)))

    return JudgeOutput(
        final_verdict=verdict,
        confidence=final_confidence,
        summary=summary,
        key_drivers=key_drivers,
    )

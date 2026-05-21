from __future__ import annotations

import re
from typing import Optional

from finance_mcp.reasoning.schemas import AgentOutput, JudgeVerdict

STRONG_THRESHOLD = 15.0
LEAN_THRESHOLD = 8.0
MIXED_THRESHOLD = 8.0
MIN_CONFIDENCE_FOR_DIRECTIONAL = 45.0

FORBIDDEN_PHRASES = frozenset(
    {
        "it depends",
        "on the other hand",
        "however one could argue",
        "mixed signals",
        "uncertain",
        "could go either way",
        "some analysts believe",
        "it remains to be seen",
    }
)


def _as_percent(confidence: float) -> float:
    """Normalize confidence from either 0-1 or 0-100 scale to 0-100."""
    bounded = max(0.0, min(float(confidence), 100.0))
    if bounded <= 1.0:
        return round(bounded * 100.0, 1)
    return round(bounded, 1)


def _sentences(text: str) -> list[str]:
    """Split agent analysis into compact candidate driver sentences."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+|[;\n]+", cleaned)
    return [part.strip(" -•\t.") for part in parts if part.strip(" -•\t.")]


def _extract_top_3(analysis: str, signals: list[str], sentiment: str) -> list[str]:
    """Extract exactly three concise drivers from signals and analysis text."""
    candidates: list[str] = []
    candidates.extend(signals)
    candidates.extend(_sentences(analysis))

    drivers: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(str(candidate).split()).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        drivers.append(normalized[:220])
        if len(drivers) == 3:
            break

    fallback_prefix = "Upside" if sentiment == "positive" else "Downside"
    while len(drivers) < 3:
        drivers.append(f"{fallback_prefix} evidence is limited; monitor fresh MCP signals.")

    return drivers


def _sanitize_summary(summary: str) -> str:
    """Remove forbidden hedging phrases from a generated summary."""
    sanitized = summary
    for phrase in FORBIDDEN_PHRASES:
        sanitized = re.sub(re.escape(phrase), "the evidence shows", sanitized, flags=re.IGNORECASE)
    return sanitized


_SIGNAL_SKIP = frozenset({"unavailable", "returned 0", "graph may", "graph unreachable", "targeting bull"})


def _pick_lead_signal(signals: list[str], analysis: str, sentiment: str) -> str:
    """Return the most informative signal, skipping infrastructure noise."""
    for s in signals:
        lower = s.lower()
        if not any(kw in lower for kw in _SIGNAL_SKIP):
            return s
    return _extract_top_3(analysis, [], sentiment)[0]


def _generate_summary(
    verdict: str,
    conviction: str,
    bull_analysis: str,
    bear_analysis: str,
    bull_rebuttal: Optional[str] = None,
    attack_target: Optional[str] = None,
    bull_signals: Optional[list[str]] = None,
    bear_signals: Optional[list[str]] = None,
) -> str:
    """Generate a decisive, specific three-sentence verdict summary."""
    bull_reason = _pick_lead_signal(bull_signals or [], bull_analysis, "positive")
    bear_risk = _pick_lead_signal(bear_signals or [], bear_analysis, "negative")

    debate_note = ""
    if attack_target:
        debate_note = f" Bear challenged '{attack_target}'."
        if bull_rebuttal:
            debate_note += f" {bull_rebuttal}"

    summary = (
        f"{verdict} with {conviction} conviction. Key bull signal: {bull_reason}. "
        f"Key bear risk: {bear_risk}."
        f"{debate_note} "
        "Thesis horizon: 3-6 months."
    )
    return _sanitize_summary(summary)


def _extract_key_drivers(
    bull_analysis: str,
    bear_analysis: str,
    bull_signals: list[str],
    bear_signals: list[str],
    bull_wins: bool,
) -> dict[str, object]:
    """Extract exactly three bull and three bear drivers."""
    return {
        "bull_drivers": _extract_top_3(bull_analysis, bull_signals, sentiment="positive"),
        "bear_drivers": _extract_top_3(bear_analysis, bear_signals, sentiment="negative"),
        "dominant_side": "bull" if bull_wins else "bear",
    }


def _compute_verdict(
    bull_confidence: float,
    bear_confidence: float,
    bull_analysis: str,
    bear_analysis: str,
    bull_signals: list[str] | None = None,
    bear_signals: list[str] | None = None,
    bull_rebuttal: Optional[str] = None,
    attack_target: Optional[str] = None,
) -> JudgeVerdict:
    bull_confidence = _as_percent(bull_confidence)
    bear_confidence = _as_percent(bear_confidence)
    gap = abs(bull_confidence - bear_confidence)
    bull_wins = bull_confidence > bear_confidence

    if gap >= STRONG_THRESHOLD and max(bull_confidence, bear_confidence) >= MIN_CONFIDENCE_FOR_DIRECTIONAL:
        verdict = "STRONG BUY" if bull_wins else "STRONG SELL"
        conviction = "HIGH"
    elif gap >= LEAN_THRESHOLD and max(bull_confidence, bear_confidence) >= MIN_CONFIDENCE_FOR_DIRECTIONAL:
        verdict = "BUY" if bull_wins else "SELL"
        conviction = "MODERATE"
    elif gap < MIXED_THRESHOLD and bull_confidence >= 50 and bear_confidence >= 50:
        verdict = "HOLD"
        conviction = "LOW - Genuinely contested thesis"
    elif max(bull_confidence, bear_confidence) < MIN_CONFIDENCE_FOR_DIRECTIONAL:
        verdict = "INSUFFICIENT DATA"
        conviction = "VERY LOW - More data required for a confident recommendation"
    else:
        verdict = "HOLD"
        conviction = "LOW"

    composite_confidence = round((max(bull_confidence, bear_confidence) * 0.65) + (gap * 0.35), 1)

    return JudgeVerdict(
        verdict=verdict,
        conviction=conviction,
        bull_confidence=bull_confidence,
        bear_confidence=bear_confidence,
        confidence_gap=round(gap, 1),
        composite_confidence=min(composite_confidence, 95.0),
        summary=_generate_summary(
            verdict, conviction, bull_analysis, bear_analysis,
            bull_rebuttal=bull_rebuttal, attack_target=attack_target,
            bull_signals=bull_signals, bear_signals=bear_signals,
        ),
        key_drivers=_extract_key_drivers(
            bull_analysis=bull_analysis,
            bear_analysis=bear_analysis,
            bull_signals=bull_signals or [],
            bear_signals=bear_signals or [],
            bull_wins=bull_wins,
        ),
    )


def run_judge_agent(
    bull_case: AgentOutput,
    bear_case: AgentOutput,
    bull_rebuttal: Optional[str] = None,
) -> JudgeVerdict:
    """Synthesize full debate transcript into a decisive final verdict."""
    return _compute_verdict(
        bull_confidence=bull_case.confidence,
        bear_confidence=bear_case.confidence,
        bull_analysis=bull_case.reasoning,
        bear_analysis=bear_case.reasoning,
        bull_signals=bull_case.signals,
        bear_signals=bear_case.signals,
        bull_rebuttal=bull_rebuttal,
        attack_target=bear_case.metadata.get("attack_target"),
    )

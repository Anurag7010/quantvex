from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    query: str
    ticker: str | None = None
    context: Dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    stance: str  # "bull" or "bear"
    reasoning: str
    signals: List[str] = Field(default_factory=list)
    confidence: float


class JudgeVerdict(BaseModel):
    verdict: str
    conviction: str
    bull_confidence: float
    bear_confidence: float
    confidence_gap: float
    composite_confidence: float
    summary: str
    key_drivers: Dict[str, Any]
    time_horizon: str = "3-6 months"
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


JudgeOutput = JudgeVerdict

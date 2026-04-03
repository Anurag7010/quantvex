from __future__ import annotations

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


class JudgeOutput(BaseModel):
    final_verdict: str
    confidence: float
    summary: str
    key_drivers: List[str] = Field(default_factory=list)

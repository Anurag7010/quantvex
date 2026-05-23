"""
finance_mcp.edgar.supplier_extractor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Groq Llama-3.3 extraction of supplier / customer relationships from 10-K filing text.

Public API
----------
async def extract_supplier_relationships(
    filing_text: str, ticker: str
) -> List[SupplierRelationship]
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List

from openai import AsyncOpenAI

from mcp_server.config import get_settings

logger = logging.getLogger(__name__)

_MAX_FILING_CHARS = 12_000  # cap before sending to Groq (~3 000 tokens)

_SYSTEM_PROMPT = (
    "You are a financial analyst specialised in supply chain risk. "
    "Extract explicit supplier and customer relationships from 10-K filings. "
    "Return ONLY a valid JSON object — no markdown, no commentary."
)

_USER_PROMPT = """\
Company ticker: {ticker}

10-K excerpt (Business + Risk Factors sections):
{filing_text}

Identify every company that is explicitly named as a supplier or customer of {ticker}.

Return a JSON object with a single key "relationships" whose value is an array. \
Each element must have exactly these keys:
  "supplier_ticker"     – stock ticker (uppercase); use "UNKNOWN" if not publicly traded
  "supplier_name"       – full legal company name
  "relationship_type"   – exactly "supplier" or "customer"
  "dependency_strength" – float 0.0–1.0 (1.0 = sole source / critical dependency)
  "evidence_quote"      – verbatim quote from the filing, ≤ 120 characters

Rules:
- Include ONLY companies explicitly named in the filing text — no inference.
- If no relationships are found return {{"relationships": []}}.
- Do not include {ticker} itself in the array.
"""


@dataclass
class SupplierRelationship:
    supplier_ticker: str
    supplier_name: str
    relationship_type: str     # "supplier" | "customer"
    dependency_strength: float  # 0.0 – 1.0
    evidence_quote: str


async def extract_supplier_relationships(
    filing_text: str,
    ticker: str,
) -> List[SupplierRelationship]:
    """
    Call Groq Llama-3.3 to extract named supplier/customer relationships from 10-K text.

    Returns an empty list if the Groq key is absent, if the model returns
    no relationships, or if parsing fails — never raises.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        logger.warning("edgar_extractor: GROQ_API_KEY not set — returning empty relationships")
        return []

    client = AsyncOpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
    )
    user_content = _USER_PROMPT.format(
        ticker=ticker,
        filing_text=filing_text[:_MAX_FILING_CHARS],
    )

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        raw: str = response.choices[0].message.content or "{}"
    except Exception as exc:
        logger.error("edgar_extractor_gpt_error ticker=%s error=%s", ticker, exc)
        return []

    try:
        parsed = json.loads(raw)
        items: list = parsed.get("relationships", []) if isinstance(parsed, dict) else parsed
        relationships: List[SupplierRelationship] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            st = str(item.get("supplier_ticker", "UNKNOWN")).upper().strip()[:64]
            sn = str(item.get("supplier_name", "Unknown"))[:256].strip()
            rt = str(item.get("relationship_type", "supplier")).lower().strip()
            ds = _clamp(item.get("dependency_strength", 0.5))
            eq = str(item.get("evidence_quote", ""))[:200].strip()

            if not st or not sn or rt not in ("supplier", "customer"):
                continue
            if st == ticker.upper():
                continue  # skip self-references

            relationships.append(
                SupplierRelationship(
                    supplier_ticker=st,
                    supplier_name=sn,
                    relationship_type=rt,
                    dependency_strength=ds,
                    evidence_quote=eq,
                )
            )

        logger.info(
            "edgar_extractor: extracted %d relationships for %s",
            len(relationships), ticker,
        )
        return relationships

    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.error(
            "edgar_extractor_parse_error ticker=%s error=%s raw_preview=%s",
            ticker, exc, raw[:200],
        )
        return []


def _clamp(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5

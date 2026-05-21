"""
finance_mcp.edgar.edgar_client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Async HTTP client for SEC EDGAR.

Public API
----------
async def get_cik(ticker: str) -> Optional[str]
    Resolve ticker → 10-digit CIK string. Returns None for non-US tickers.

async def fetch_10k_filing(ticker: str) -> Tuple[str, str]
    Returns (filing_text, filing_date).
    filing_text is the Business + Risk Factors sections (≤ 24 000 chars).
    Raises EdgarError on failure.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_EDGAR_BASE = "https://www.sec.gov"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# EDGAR Fair Access Policy requires a descriptive User-Agent with contact info.
_HEADERS = {
    "User-Agent": "QuantVex/2.0 research@quantvex.ai",
    "Accept-Encoding": "gzip, deflate",
}
_TIMEOUT = 30.0
_MIN_DELAY = 0.12  # stay under EDGAR's 10 req/sec policy

_MAX_SECTION_CHARS = 12_000  # ~3 000 tokens per section, 2 sections → ~6 000 tokens total

_CIK_CACHE: dict[str, Optional[str]] = {}


class EdgarError(RuntimeError):
    """Raised when an EDGAR fetch or parse step fails."""


# ---------------------------------------------------------------------------
# CIK resolution
# ---------------------------------------------------------------------------

async def get_cik(ticker: str) -> Optional[str]:
    """
    Resolve a stock ticker to a zero-padded 10-digit CIK string.

    Returns None when the ticker is not registered with the SEC
    (e.g. TSMC, Samsung, ASML — non-US listed companies).
    Caches results in-process to avoid re-downloading the 600 KB tickers file.
    """
    ticker_upper = ticker.upper()
    if ticker_upper in _CIK_CACHE:
        return _CIK_CACHE[ticker_upper]

    async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(_TICKERS_URL)
        resp.raise_for_status()
        data: dict = resp.json()

    for entry in data.values():
        if isinstance(entry, dict) and entry.get("ticker", "").upper() == ticker_upper:
            cik_int = entry["cik_str"]
            result = str(int(cik_int)).zfill(10)
            _CIK_CACHE[ticker_upper] = result
            return result

    _CIK_CACHE[ticker_upper] = None
    return None


# ---------------------------------------------------------------------------
# 10-K filing fetch
# ---------------------------------------------------------------------------

async def fetch_10k_filing(ticker: str) -> Tuple[str, str]:
    """
    Fetch the most recent 10-K for *ticker* and return the relevant text.

    Returns
    -------
    (filing_text, filing_date)
        filing_text : str  — Business + Risk Factors sections, stripped of HTML.
        filing_date : str  — ISO-8601 date, e.g. "2024-11-01".

    Raises
    ------
    EdgarError
        • Ticker not found in EDGAR (non-US company).
        • No 10-K filing found.
        • HTTP / network failure.
    """
    cik = await get_cik(ticker)
    if not cik:
        raise EdgarError(
            f"Ticker {ticker!r} not found in EDGAR. "
            "EDGAR only covers SEC-registered (predominantly US-listed) companies."
        )

    await asyncio.sleep(_MIN_DELAY)

    # -----------------------------------------------------------------------
    # Step 1 — Fetch submissions metadata
    # -----------------------------------------------------------------------
    submissions_url = _SUBMISSIONS_URL.format(cik=cik)
    async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(submissions_url)
        resp.raise_for_status()
        submissions: dict = resp.json()

    filings = submissions.get("filings", {}).get("recent", {})
    forms: list = filings.get("form", [])
    accessions: list = filings.get("accessionNumber", [])
    dates: list = filings.get("filingDate", [])
    primary_docs: list = filings.get("primaryDocument", [])

    # Find the most recent 10-K (list is newest-first in EDGAR submissions API)
    ten_k_index: Optional[int] = None
    for i, form in enumerate(forms):
        if form == "10-K":
            ten_k_index = i
            break

    if ten_k_index is None:
        raise EdgarError(f"No 10-K filing found for {ticker} (CIK {cik}) in EDGAR.")

    accession_no = accessions[ten_k_index].replace("-", "")
    filing_date = dates[ten_k_index]
    primary_doc = primary_docs[ten_k_index]
    cik_int = int(cik)

    await asyncio.sleep(_MIN_DELAY)

    # -----------------------------------------------------------------------
    # Step 2 — Fetch the primary HTML document
    # -----------------------------------------------------------------------
    doc_url = f"{_EDGAR_BASE}/Archives/edgar/data/{cik_int}/{accession_no}/{primary_doc}"
    doc_headers = {**_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"}
    async with httpx.AsyncClient(headers=doc_headers, timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(doc_url)
        resp.raise_for_status()
        html_text: str = resp.text

    # -----------------------------------------------------------------------
    # Step 3 — Extract relevant sections
    # -----------------------------------------------------------------------
    plain = _strip_html(html_text)
    filing_text = _extract_sections(plain)
    if len(filing_text) < 10:
        # Fallback: nothing useful was extracted — return the first 20k chars
        filing_text = plain[:20_000]

    logger.info(
        "edgar_10k_fetched ticker=%s cik=%s date=%s extracted_chars=%d",
        ticker, cik, filing_date, len(filing_text),
    )
    return filing_text, filing_date


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Remove HTML/XBRL tags, decode common entities, and normalise whitespace."""
    # Remove script / style blocks entirely
    text = re.sub(r"(?i)<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode a handful of common HTML entities
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&nbsp;": " ", "&ndash;": "-", "&mdash;": "-",
        "&#160;": " ", "&#8217;": "'", "&#8220;": '"', "&#8221;": '"',
    }
    for entity, replacement in entities.items():
        text = text.replace(entity, replacement)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_sections(plain: str) -> str:
    """
    Extract Item 1 (Business) and Item 1A (Risk Factors) sections from
    plain text of a 10-K filing.
    """
    # Anchor patterns — match section headers regardless of formatting
    item1_re = re.compile(r"ITEM\s+1[\.\s]+BUSINESS\b", re.IGNORECASE)
    item1a_re = re.compile(r"ITEM\s+1A[\.\s]+RISK\s+FACTORS\b", re.IGNORECASE)
    item2_re = re.compile(r"ITEM\s+2[\.\s]+PROPERTIES?\b", re.IGNORECASE)

    m1 = item1_re.search(plain)
    m1a = item1a_re.search(plain, m1.end() if m1 else 0)
    m2 = item2_re.search(plain, m1a.end() if m1a else (m1.end() if m1 else 0))

    sections: list[str] = []

    if m1:
        end_pos = m1a.start() if m1a else (m2.start() if m2 else m1.start() + _MAX_SECTION_CHARS)
        chunk = plain[m1.start(): min(end_pos, m1.start() + _MAX_SECTION_CHARS)]
        if chunk.strip():
            sections.append(chunk)

    if m1a:
        end_pos = m2.start() if m2 else m1a.start() + _MAX_SECTION_CHARS
        chunk = plain[m1a.start(): min(end_pos, m1a.start() + _MAX_SECTION_CHARS)]
        if chunk.strip():
            sections.append(chunk)

    return "\n\n---\n\n".join(sections)

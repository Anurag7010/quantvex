"""
finance_mcp.causal.price_fetcher
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Async wrapper around yfinance for daily close price downloads.

Public API
----------
async def fetch_price_history(ticker: str, years: int = 2) -> pd.DataFrame
    Returns a DataFrame with DatetimeIndex and a single 'Close' column.
    Returns an empty DataFrame when no data is available.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Ordered list of exchange suffixes to try for non-US tickers.
# Bare ticker ("") is always tried first.
_EXCHANGE_SUFFIXES = ["", ".NS", ".BO", ".KS", ".T", ".L", ".AX"]

_DEFAULT_YEARS = 2


async def fetch_price_history(
    ticker: str,
    years: int = _DEFAULT_YEARS,
) -> pd.DataFrame:
    """
    Fetch daily close prices for *ticker* via yfinance.

    Tries the bare ticker first, then common exchange suffixes for non-US
    stocks (e.g. ".KS" for Korean, ".T" for Tokyo).

    Returns
    -------
    pd.DataFrame
        DatetimeIndex, single column ``Close``.  Empty if no data found.
    """
    period = f"{years}y"

    for suffix in _EXCHANGE_SUFFIXES:
        qualified = f"{ticker}{suffix}"
        try:
            df = await asyncio.to_thread(_download, qualified, period)
            if df is not None and not df.empty:
                logger.info("price_fetch ok ticker=%s rows=%d", qualified, len(df))
                return df
        except Exception as exc:
            logger.debug("price_fetch failed ticker=%s: %s", qualified, exc)

    logger.warning("price_fetch no data ticker=%s", ticker)
    return pd.DataFrame()


def _download(ticker: str, period: str) -> Optional[pd.DataFrame]:
    """Synchronous yfinance download, called via asyncio.to_thread."""
    raw = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        return None
    # yfinance >= 0.2 sometimes returns MultiIndex columns
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    if "Close" not in raw.columns:
        return None
    return raw[["Close"]].dropna()

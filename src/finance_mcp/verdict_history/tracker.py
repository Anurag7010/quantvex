"""
Verdict tracker — record verdicts to SQLite and schedule async price-accuracy checks.

Usage
-----
    verdict_id = await record_verdict({
        "ticker": "NVDA",
        "query": "NVDA supply chain risk",
        "verdict": "BUY",
        "confidence": 0.72,
        "price_at_verdict": 875.50,
    })

Background tasks check the price 5 and 30 trading days later and write
``correct_5d`` / ``correct_30d`` (1 = direction correct, 0 = wrong) back into
the SQLite row.  HOLD and INSUFFICIENT DATA verdicts are skipped (no direction
to validate).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from finance_mcp.verdict_history.db import _DEFAULT_DB_PATH, get_connection

logger = logging.getLogger(__name__)

# Trading seconds per day (approximate; avoids calendar logic)
_TRADING_DAY_SECONDS = 86_400

_DIRECTIONAL_VERDICTS = {"STRONG BUY", "BUY", "SELL", "STRONG SELL"}
_BULLISH_VERDICTS = {"STRONG BUY", "BUY"}
_BEARISH_VERDICTS = {"SELL", "STRONG SELL"}


def _write_verdict_sync(row: Dict[str, Any], db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO verdicts
               (id, ticker, query, verdict, confidence, created_at, price_at_verdict)
               VALUES (:id, :ticker, :query, :verdict, :confidence, :created_at, :price_at_verdict)""",
            row,
        )
        conn.commit()
    finally:
        conn.close()


def _update_price_sync(
    verdict_id: str,
    column: str,
    price: float,
    correct: Optional[int],
    db_path: str,
) -> None:
    conn = get_connection(db_path)
    try:
        if column == "correct_5d":
            sql = "UPDATE verdicts SET price_5d = ?, correct_5d = ? WHERE id = ?"
        else:
            sql = "UPDATE verdicts SET price_30d = ?, correct_30d = ? WHERE id = ?"
        conn.execute(sql, (price, correct, verdict_id))
        conn.commit()
    finally:
        conn.close()


def _is_correct(verdict: str, price_at: float, price_now: float) -> int:
    """Return 1 if price moved in the predicted direction (±2% tolerance for BUY/SELL)."""
    pct_change = (price_now - price_at) / price_at if price_at else 0.0
    if verdict in _BULLISH_VERDICTS:
        return 1 if pct_change > 0.02 else 0
    if verdict in _BEARISH_VERDICTS:
        return 1 if pct_change < -0.02 else 0
    return 0


async def _fetch_current_price(ticker: str) -> Optional[float]:
    """Fetch the latest close via yfinance (sync call wrapped in thread)."""
    try:
        import yfinance as yf

        def _download() -> Optional[float]:
            df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty:
                return None
            close_col = "Close"
            if hasattr(df.columns, "get_level_values"):
                df.columns = df.columns.get_level_values(0)
            if close_col not in df.columns:
                return None
            return float(df[close_col].dropna().iloc[-1])

        return await asyncio.to_thread(_download)
    except Exception as exc:
        logger.warning("price_check_fetch_failed ticker=%s error=%s", ticker, exc)
        return None


async def _schedule_price_updates(
    verdict_id: str,
    ticker: str,
    verdict: str,
    price_at_verdict: Optional[float],
    db_path: str,
) -> None:
    """Background task: check price 5d and 30d after verdict, write accuracy."""
    if not ticker or verdict not in _DIRECTIONAL_VERDICTS or not price_at_verdict:
        return

    # 5-day check
    await asyncio.sleep(5 * _TRADING_DAY_SECONDS)
    price_5d = await _fetch_current_price(ticker)
    if price_5d is not None:
        correct_5d = _is_correct(verdict, price_at_verdict, price_5d)
        await asyncio.to_thread(
            _update_price_sync, verdict_id, "correct_5d", price_5d, correct_5d, db_path
        )
        logger.info(
            "verdict_5d_check",
            verdict_id=verdict_id,
            ticker=ticker,
            price_5d=price_5d,
            correct_5d=correct_5d,
        )

    # 30-day check (wait an additional 25 trading days)
    await asyncio.sleep(25 * _TRADING_DAY_SECONDS)
    price_30d = await _fetch_current_price(ticker)
    if price_30d is not None:
        correct_30d = _is_correct(verdict, price_at_verdict, price_30d)
        await asyncio.to_thread(
            _update_price_sync, verdict_id, "correct_30d", price_30d, correct_30d, db_path
        )
        logger.info(
            "verdict_30d_check",
            verdict_id=verdict_id,
            ticker=ticker,
            price_30d=price_30d,
            correct_30d=correct_30d,
        )


async def record_verdict(
    verdict_data: Dict[str, Any],
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """
    Persist a verdict to SQLite and schedule background accuracy checks.

    Parameters
    ----------
    verdict_data : dict
        Must contain: ``ticker``, ``query``, ``verdict``, ``confidence``.
        Optional: ``price_at_verdict`` (float).
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    str
        UUID4 of the newly created verdict row.
    """
    verdict_id = str(uuid.uuid4())
    row = {
        "id": verdict_id,
        "ticker": (verdict_data.get("ticker") or "").strip().upper(),
        "query": verdict_data.get("query") or "",
        "verdict": verdict_data.get("verdict"),
        "confidence": verdict_data.get("confidence"),
        "created_at": datetime.utcnow().isoformat(),
        "price_at_verdict": verdict_data.get("price_at_verdict"),
    }

    await asyncio.to_thread(_write_verdict_sync, row, db_path)

    logger.info(
        "verdict_recorded",
        verdict_id=verdict_id,
        ticker=row["ticker"],
        verdict=row["verdict"],
    )

    # Spawn background accuracy-check task (fire-and-forget)
    asyncio.create_task(
        _schedule_price_updates(
            verdict_id=verdict_id,
            ticker=row["ticker"],
            verdict=row["verdict"] or "",
            price_at_verdict=row["price_at_verdict"],
            db_path=db_path,
        )
    )

    return verdict_id

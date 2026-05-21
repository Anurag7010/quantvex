"""
Verdict accuracy calculator — queries the SQLite store for per-verdict-type accuracy.

Returns accuracy at 5-day and 30-day windows with sample sizes.
Only rows where ``correct_5d`` / ``correct_30d`` are non-NULL are included in
accuracy calculations; rows with pending checks are counted in ``n`` but not
in the accuracy percentage.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from finance_mcp.verdict_history.db import _DEFAULT_DB_PATH, get_connection


def compute_accuracy_stats(db_path: str = _DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Compute per-verdict-type accuracy statistics.

    Returns
    -------
    dict
        Keyed by verdict string (e.g. "STRONG BUY"). Each value is::

            {
                "5d":  float | None,   # accuracy % (0–100) or None if no resolved rows
                "30d": float | None,
                "n":   int             # total verdicts of this type (including pending)
            }
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT
                verdict,
                COUNT(*)                                                     AS n,
                SUM(CASE WHEN correct_5d  = 1 THEN 1 ELSE 0 END)            AS correct_5d_count,
                SUM(CASE WHEN correct_5d  IS NOT NULL THEN 1 ELSE 0 END)    AS resolved_5d,
                SUM(CASE WHEN correct_30d = 1 THEN 1 ELSE 0 END)            AS correct_30d_count,
                SUM(CASE WHEN correct_30d IS NOT NULL THEN 1 ELSE 0 END)    AS resolved_30d
            FROM verdicts
            WHERE verdict IS NOT NULL
            GROUP BY verdict
            """
        )
        stats: Dict[str, Any] = {}
        for row in cursor.fetchall():
            acc_5d: Optional[float] = (
                round(row["correct_5d_count"] / row["resolved_5d"] * 100, 1)
                if row["resolved_5d"] > 0
                else None
            )
            acc_30d: Optional[float] = (
                round(row["correct_30d_count"] / row["resolved_30d"] * 100, 1)
                if row["resolved_30d"] > 0
                else None
            )
            stats[row["verdict"]] = {
                "5d": acc_5d,
                "30d": acc_30d,
                "n": row["n"],
            }
        return stats
    finally:
        conn.close()

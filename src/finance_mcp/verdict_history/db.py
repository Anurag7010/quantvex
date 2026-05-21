"""
SQLite schema and connection helpers for the verdict history store.

Schema
------
verdicts table:
  id            TEXT PRIMARY KEY  — UUID4
  ticker        TEXT NOT NULL     — uppercase ticker (or "" if unknown)
  query         TEXT              — original analysis query
  verdict       TEXT              — STRONG BUY | BUY | HOLD | SELL | STRONG SELL | INSUFFICIENT DATA
  confidence    REAL              — composite confidence in [0, 1]
  created_at    TEXT              — ISO-8601 UTC timestamp
  price_at_verdict REAL           — market price when verdict was recorded (NULL if unavailable)
  price_5d      REAL              — market price ~5 trading days later (populated by background task)
  price_30d     REAL              — market price ~30 trading days later
  correct_5d    INTEGER           — 1 if price moved in predicted direction; 0 if not; NULL if pending
  correct_30d   INTEGER           — same for 30-day window
"""

import sqlite3
import os
from typing import Optional

_DEFAULT_DB_PATH: str = os.environ.get("VERDICT_DB_PATH", "verdicts.db")

_DDL = """
CREATE TABLE IF NOT EXISTS verdicts (
    id               TEXT PRIMARY KEY,
    ticker           TEXT NOT NULL,
    query            TEXT,
    verdict          TEXT,
    confidence       REAL,
    created_at       TEXT,
    price_at_verdict REAL,
    price_5d         REAL,
    price_30d        REAL,
    correct_5d       INTEGER,
    correct_30d      INTEGER
);
"""


def get_connection(db_path: str = _DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return a sqlite3 connection with Row factory enabled."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db(db_path: str = _DEFAULT_DB_PATH) -> None:
    """Create the verdicts table if it does not already exist."""
    with get_connection(db_path) as conn:
        conn.execute(_DDL)
        conn.commit()

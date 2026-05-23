"""
GraphClient — Memgraph/Neo4j Bolt client for the supply chain graph.

Uses the `neo4j` Python driver (Bolt protocol, port 7687).  Memgraph speaks
Bolt natively and is fully compatible with this driver.

SECURITY MODEL
--------------
• All queries use parameterized Cypher — user-supplied values travel through
  the driver's parameter binding layer and are never string-interpolated into
  query text.

• The sole exception is the `max_hops` integer embedded via an f-string in
  `_trace_company_impact()`.  This is safe because:
    1. The value is validated as a Python int in [1, 5] before the f-string.
    2. A bounded integer literal cannot carry Cypher injection.

• VID-like identifiers (tickers, commodity IDs, event IDs) are validated
  against ^[A-Za-z0-9_.-]{1,64}$ before being passed as query parameters,
  providing defence-in-depth on top of the driver's parameterisation.

PUBLIC API
----------
Mirrors the old SecureGraphClient surface so that invoke handlers and the
ingestion pipeline require no changes:

  fetch_company(ticker) → dict
  fetch_commodity(commodity_id) → dict
  fetch_event(event_id) → dict
  insert_company(ticker, name, sector) → bool
  insert_commodity(commodity_id, name, category) → bool
  upsert_event(event_id, description, severity) → bool
  insert_depends_on(src_ticker, dst_ticker, weight) → bool
  insert_requires(ticker, commodity_id, volume) → bool
  insert_impacts(event_id, target_vid, impact_time) → bool
  trace_impact(target_ticker, max_hops) → List[dict]
  find_companies_requiring(commodity_id) → List[dict]
  ping() → bool
  initialize_pool() / close() / context manager
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level defaults (override via env or constructor args)
# ---------------------------------------------------------------------------
DEFAULT_HOST: str = os.environ.get("MEMGRAPH_HOST", "localhost")
DEFAULT_PORT: int = int(os.environ.get("MEMGRAPH_PORT", "7687"))
AGENT_USER: str = os.environ.get("MEMGRAPH_USER", "")
AGENT_PASSWORD: str = os.environ.get("MEMGRAPH_PASSWORD", "")

# VID validation — alphanumeric + underscore, dot, hyphen; 1–64 chars.
_VID_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')


def _validate_vid(value: str, field: str = "vid") -> None:
    if not isinstance(value, str) or not _VID_RE.match(value):
        raise ValueError(
            f"{field!r} must be a string of 1–64 characters containing only "
            f"alphanumeric characters, underscores, dots, or hyphens. "
            f"Got: {value!r}"
        )


def _validate_str(value: Any, field: str, max_len: int, required: bool = True) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field!r} must be a str, got {type(value).__name__}")
    if required and not value.strip():
        raise ValueError(f"{field!r} must not be empty")
    if len(value) > max_len:
        raise ValueError(
            f"{field!r} must be at most {max_len} characters, got {len(value)}"
        )


# ---------------------------------------------------------------------------
# GraphClient
# ---------------------------------------------------------------------------

class GraphClient:
    """
    Connection-pooled Memgraph client for the supply chain graph.

    Usage — context manager::

        with GraphClient() as client:
            result = client.fetch_company("AAPL")

    Usage — explicit lifecycle::

        client = GraphClient()
        client.initialize_pool()
        try:
            ...
        finally:
            client.close()
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        user: str = AGENT_USER,
        password: str = AGENT_PASSWORD,
    ) -> None:
        neo4j_uri = os.environ.get("NEO4J_URI", "")
        self._uri = neo4j_uri if neo4j_uri else f"bolt://{host}:{port}"
        self._user = user
        self._password = password
        self._driver: Optional[Driver] = None

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    def initialize_pool(self) -> None:
        if self._driver is not None:
            return
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        logger.info("GraphClient: connected — %s", self._uri)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("GraphClient: closed")

    def __enter__(self) -> "GraphClient":
        self.initialize_pool()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Internal execution
    # ------------------------------------------------------------------ #

    def _run(self, query: str, **params: Any) -> List[Dict]:
        if self._driver is None:
            raise RuntimeError(
                "GraphClient: not initialised. "
                "Call initialize_pool() or use the context manager."
            )
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    # ------------------------------------------------------------------ #
    # Connectivity
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        try:
            self._run("RETURN 1 AS ok")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Vertex reads
    # ------------------------------------------------------------------ #

    def fetch_company(self, ticker: str) -> Dict:
        _validate_vid(ticker, "ticker")
        records = self._run(
            "MATCH (c:Company {ticker: $ticker}) "
            "RETURN c.ticker AS ticker, c.name AS name, c.sector AS sector",
            ticker=ticker,
        )
        return records[0] if records else {}

    def fetch_commodity(self, commodity_id: str) -> Dict:
        _validate_vid(commodity_id, "commodity_id")
        records = self._run(
            "MATCH (c:Commodity {commodity_id: $commodity_id}) "
            "RETURN c.commodity_id AS commodity_id, c.name AS name, c.category AS category",
            commodity_id=commodity_id,
        )
        return records[0] if records else {}

    def fetch_event(self, event_id: str) -> Dict:
        _validate_vid(event_id, "event_id")
        records = self._run(
            "MATCH (e:Event {event_id: $event_id}) "
            "RETURN e.event_id AS event_id, e.description AS description, e.severity AS severity",
            event_id=event_id,
        )
        return records[0] if records else {}

    # ------------------------------------------------------------------ #
    # Vertex writes (MERGE = idempotent upsert)
    # ------------------------------------------------------------------ #

    def insert_company(self, ticker: str, name: str, sector: str = "") -> bool:
        _validate_vid(ticker, "ticker")
        _validate_str(name, "name", max_len=256)
        _validate_str(sector, "sector", max_len=128, required=False)
        self._run(
            "MERGE (c:Company {ticker: $ticker}) "
            "SET c.name = $name, c.sector = $sector",
            ticker=ticker, name=name, sector=sector,
        )
        logger.info("insert_company: %r", ticker)
        return True

    def insert_commodity(
        self,
        commodity_id: str,
        name: str,
        category: str = "",
    ) -> bool:
        _validate_vid(commodity_id, "commodity_id")
        _validate_str(name, "name", max_len=256)
        _validate_str(category, "category", max_len=128, required=False)
        self._run(
            "MERGE (c:Commodity {commodity_id: $commodity_id}) "
            "SET c.name = $name, c.category = $category",
            commodity_id=commodity_id, name=name, category=category,
        )
        logger.info("insert_commodity: %r", commodity_id)
        return True

    def upsert_event(
        self,
        event_id: str,
        description: str,
        severity: int,
    ) -> bool:
        _validate_vid(event_id, "event_id")
        _validate_str(description, "description", max_len=1024)
        if not isinstance(severity, int) or not (0 <= severity <= 10):
            raise ValueError("severity must be an integer between 0 and 10 inclusive")
        self._run(
            "MERGE (e:Event {event_id: $event_id}) "
            "SET e.description = $description, e.severity = $severity",
            event_id=event_id, description=description, severity=severity,
        )
        logger.info("upsert_event: %r severity=%d", event_id, severity)
        return True

    # ------------------------------------------------------------------ #
    # Edge writes
    # ------------------------------------------------------------------ #

    def insert_depends_on(
        self,
        src_ticker: str,
        dst_ticker: str,
        weight: float = 1.0,
    ) -> bool:
        _validate_vid(src_ticker, "src_ticker")
        _validate_vid(dst_ticker, "dst_ticker")
        if not isinstance(weight, (int, float)) or not (0.0 <= float(weight) <= 1.0):
            raise ValueError("weight must be a float between 0.0 and 1.0")
        self._run(
            "MATCH (a:Company {ticker: $src}), (b:Company {ticker: $dst}) "
            "MERGE (a)-[r:DEPENDS_ON]->(b) "
            "SET r.weight = $weight",
            src=src_ticker, dst=dst_ticker, weight=float(weight),
        )
        logger.info("insert_depends_on: %r -> %r weight=%.2f", src_ticker, dst_ticker, weight)
        return True

    def insert_requires(
        self,
        ticker: str,
        commodity_id: str,
        volume: int = 0,
    ) -> bool:
        _validate_vid(ticker, "ticker")
        _validate_vid(commodity_id, "commodity_id")
        if not isinstance(volume, int) or volume < 0:
            raise ValueError("volume must be a non-negative integer")
        self._run(
            "MATCH (c:Company {ticker: $ticker}), "
            "(com:Commodity {commodity_id: $commodity_id}) "
            "MERGE (c)-[r:REQUIRES]->(com) "
            "SET r.volume = $volume",
            ticker=ticker, commodity_id=commodity_id, volume=volume,
        )
        logger.info("insert_requires: %r -> %r volume=%d", ticker, commodity_id, volume)
        return True

    def insert_impacts(
        self,
        event_id: str,
        target_vid: str,
        impact_time: Optional[str] = None,
    ) -> bool:
        _validate_vid(event_id, "event_id")
        _validate_vid(target_vid, "target_vid")
        self._run(
            "MATCH (e:Event {event_id: $event_id}) "
            "MATCH (t) WHERE "
            "  (t:Company AND t.ticker = $target) OR "
            "  (t:Commodity AND t.commodity_id = $target) "
            "MERGE (e)-[r:IMPACTS]->(t) "
            "SET r.impact_time = $impact_time",
            event_id=event_id, target=target_vid, impact_time=impact_time,
        )
        logger.info("insert_impacts: %r -> %r", event_id, target_vid)
        return True

    # ------------------------------------------------------------------ #
    # Traversal / supply-chain reasoning
    # ------------------------------------------------------------------ #

    def trace_impact(
        self,
        target_ticker: str,
        max_hops: int = 3,
    ) -> List[Dict]:
        """
        Find all companies downstream of a supply shock at `target_ticker`.

        Works for both Company tickers and Commodity IDs:
          - Commodity: find all companies requiring it, then trace their DEPENDS_ON cascade.
          - Company: traverse DEPENDS_ON edges in reverse.

        Returns list of {"ticker", "name", "sector"} dicts (deduplicated).
        """
        _validate_vid(target_ticker, "target_ticker")
        if not isinstance(max_hops, int) or not (1 <= max_hops <= 5):
            raise ValueError("max_hops must be an integer between 1 and 5 inclusive")

        # Check if target is a commodity
        commodity = self._run(
            "MATCH (c:Commodity {commodity_id: $cid}) RETURN c.commodity_id AS id",
            cid=target_ticker,
        )
        if commodity:
            requiring = self.find_companies_requiring(target_ticker)
            impacted: Dict[str, Dict] = {}
            for company in requiring:
                impacted[company["ticker"]] = company
                for downstream in self._trace_company_impact(company["ticker"], max_hops):
                    impacted[downstream["ticker"]] = downstream
            result = list(impacted.values())
            logger.info(
                "trace_impact: commodity=%r max_hops=%d found=%d",
                target_ticker, max_hops, len(result),
            )
            return result

        return self._trace_company_impact(target_ticker, max_hops)

    def _trace_company_impact(
        self,
        target_ticker: str,
        max_hops: int,
    ) -> List[Dict]:
        query = (
            f"MATCH (impacted:Company)-[:DEPENDS_ON*1..{max_hops}]"
            f"->(target:Company {{ticker: $ticker}}) "
            "RETURN DISTINCT impacted.ticker AS ticker, "
            "impacted.name AS name, impacted.sector AS sector"
        )
        records = self._run(query, ticker=target_ticker)

        # Enrich with causal edge properties for direct (1-hop) dependents
        causal_map = self._get_direct_causal_props(target_ticker)
        for record in records:
            props = causal_map.get(record["ticker"], {})
            record["beta"] = props.get("beta")
            record["lag_days"] = props.get("lag_days")
            record["r_squared"] = props.get("r_squared")

        logger.info(
            "trace_impact: target=%r max_hops=%d found=%d",
            target_ticker, max_hops, len(records),
        )
        return records

    def _get_direct_causal_props(self, target_ticker: str) -> Dict[str, Dict]:
        """Return causal edge properties for all direct (1-hop) dependents of target."""
        records = self._run(
            "MATCH (dep:Company)-[r:DEPENDS_ON]->(target:Company {ticker: $ticker}) "
            "RETURN dep.ticker AS ticker, r.beta AS beta, "
            "r.lag_days AS lag_days, r.r_squared AS r_squared",
            ticker=target_ticker,
        )
        return {r["ticker"]: r for r in records}

    def get_all_depends_on_edges(self) -> List[Dict]:
        """Return all DEPENDS_ON edges as list of {src, dst, weight} dicts."""
        return self._run(
            "MATCH (a:Company)-[r:DEPENDS_ON]->(b:Company) "
            "RETURN a.ticker AS src, b.ticker AS dst, r.weight AS weight"
        )

    def update_edge_causal(
        self,
        src_ticker: str,
        dst_ticker: str,
        beta: float,
        lag_days: int,
        r_squared: float,
    ) -> bool:
        """Write causal properties onto an existing DEPENDS_ON edge."""
        _validate_vid(src_ticker, "src_ticker")
        _validate_vid(dst_ticker, "dst_ticker")
        self._run(
            "MATCH (a:Company {ticker: $src})-[r:DEPENDS_ON]->(b:Company {ticker: $dst}) "
            "SET r.beta = $beta, r.lag_days = $lag_days, r.r_squared = $r_squared",
            src=src_ticker, dst=dst_ticker,
            beta=float(beta), lag_days=int(lag_days), r_squared=float(r_squared),
        )
        logger.info(
            "update_edge_causal: %r->%r beta=%.4f lag=%d r2=%.4f",
            src_ticker, dst_ticker, beta, lag_days, r_squared,
        )
        return True

    def find_companies_requiring(self, commodity_id: str) -> List[Dict]:
        _validate_vid(commodity_id, "commodity_id")
        records = self._run(
            "MATCH (c:Company)-[:REQUIRES]->(com:Commodity {commodity_id: $commodity_id}) "
            "RETURN c.ticker AS ticker, c.name AS name, c.sector AS sector",
            commodity_id=commodity_id,
        )
        logger.info(
            "find_companies_requiring: commodity=%r found=%d",
            commodity_id, len(records),
        )
        return records

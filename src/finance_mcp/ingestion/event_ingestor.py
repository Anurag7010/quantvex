"""
finance_mcp.ingestion.event_ingestor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Writes ParsedEvent objects into the NebulaGraph supply chain graph.

Pipeline
--------
ParsedEvent
    │
    ▼  upsert_event(event_id, description, severity)
Event vertex in NebulaGraph
    │
    ▼  insert_impacts(src=event_id, dst=entity_id, impact_time=...)
IMPACTS edge → Company / Commodity vertex

Design
------
* Uses SecureGraphClient (Phase 2) for all graph interaction — no direct
  nGQL strings are built here.
* A thin private subclass _GraphWriter adds insert_impacts() without
  touching the Phase 2 source.
* One connection pool is opened per ingest() call and closed in a
  finally block to guarantee cleanup.
* Per-event failures are captured and returned in IngestResult without
  aborting the rest of the batch.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from finance_mcp.graph.client import (
    SecureGraphClient,
    DEFAULT_HOST,
    DEFAULT_PORT,
    AGENT_USER,
    AGENT_PASSWORD,
)
from finance_mcp.news.event_parser import ParsedEvent

logger = logging.getLogger(__name__)

# VID validation — identical pattern to SecureGraphClient._validate_vid
_VID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")

# INSERT IMPACTS with Python {src}/{dst} format slots for VID literals.
# NebulaGraph does not support $param syntax in VID position, so validated
# VIDs are embedded as quoted literals (same pattern as INSERT_COMPANY).
_INSERT_IMPACTS_FMT = (
    'INSERT EDGE IF NOT EXISTS IMPACTS(impact_time) '
    'VALUES "{src}"->"{dst}":(datetime($impact_time))'
)


# ---------------------------------------------------------------------------
# Private graph writer — adds INSERT_IMPACTS edge support
# ---------------------------------------------------------------------------

class _GraphWriter(SecureGraphClient):
    """
    Minimal subclass of SecureGraphClient that exposes an insert_impacts()
    method.  The query string comes from the immutable queries module
    (satisfying the Phase 2 safety contract); all values travel through
    the params dict to _execute() at the protocol level.
    """

    def insert_impacts(self, src: str, dst: str, impact_time: str) -> None:
        """
        Insert an IMPACTS edge from an Event vertex to a Company or
        Commodity vertex.

        Parameters
        ----------
        src         : str — Event VID (e.g. "EVT_abc123def456")
        dst         : str — Company or Commodity VID (e.g. "TSMC", "LITHIUM")
        impact_time : str — ISO-8601 datetime, e.g. "2026-03-09T00:00:00"
        """
        if not _VID_RE.match(src):
            raise ValueError(f"insert_impacts: invalid src VID {src!r}")
        if not _VID_RE.match(dst):
            raise ValueError(f"insert_impacts: invalid dst VID {dst!r}")
        # VIDs are validated above — safe to embed as quoted literals.
        # impact_time travels through params to execute_parameter().
        self._execute(
            _INSERT_IMPACTS_FMT.format(src=src, dst=dst),
            {"impact_time": impact_time},
        )


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass
class IngestResult:
    """Summary statistics returned by EventIngestor.ingest()."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# EventIngestor
# ---------------------------------------------------------------------------

class EventIngestor:
    """
    Persists a batch of ParsedEvent objects into NebulaGraph.

    Usage::

        ingestor = EventIngestor(host="127.0.0.1", port=9669)
        result = ingestor.ingest(parsed_events)
        print(result.succeeded, "events written")

    Parameters
    ----------
    host     : str  NebulaGraph host  (default: "127.0.0.1")
    port     : int  NebulaGraph port  (default: 9669)
    user     : str  Graph user        (default: "root")
    password : str  Graph password    (default: "nebula")
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        user: str = AGENT_USER,
        password: str = AGENT_PASSWORD,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password

    # ------------------------------------------------------------------

    def ingest_event(self, parsed_event: ParsedEvent) -> IngestResult:
        """
        Write a single ParsedEvent to the graph.

        Convenience wrapper around :meth:`ingest` for callers that
        process events one at a time (e.g. a streaming consumer).

        Parameters
        ----------
        parsed_event : ParsedEvent
            A single event produced by EventParser.parse_news_article().

        Returns
        -------
        IngestResult
            ``succeeded=1`` on success; ``failed=1`` with error message
            on failure.
        """
        return self.ingest([parsed_event])

    # ------------------------------------------------------------------

    def ingest(self, events: List[ParsedEvent]) -> IngestResult:
        """
        Write each ParsedEvent to the graph.

        Opens a single connection pool for the whole batch.  Individual
        event failures are logged and captured in IngestResult.errors
        without aborting the remaining events.

        Parameters
        ----------
        events : List[ParsedEvent]
            Events produced by EventParser.parse_articles().

        Returns
        -------
        IngestResult
            Counts and error messages for the batch.
        """
        result = IngestResult(total=len(events))

        if not events:
            return result

        client = _GraphWriter(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
        )

        try:
            client.initialize_pool()
            for event in events:
                try:
                    self._ingest_one(client, event)
                    result.succeeded += 1
                except Exception as exc:
                    result.failed += 1
                    msg = f"{event.event_id}: {exc}"
                    result.errors.append(msg)
                    logger.warning("ingest failed — %s", msg)
        finally:
            client.close()

        logger.info(
            "ingest complete: total=%d ok=%d failed=%d",
            result.total,
            result.succeeded,
            result.failed,
        )
        return result

    # ------------------------------------------------------------------

    def _ingest_one(self, client: _GraphWriter, event: ParsedEvent) -> None:
        """
        Write a single ParsedEvent: upsert the Event vertex then insert
        one IMPACTS edge per impacted entity.
        """
        client.upsert_event(
            event_id=event.event_id,
            description=event.description,
            severity=event.severity,
        )

        impact_time = event.published_at.strftime("%Y-%m-%dT%H:%M:%S")

        for entity in event.impacted_entities:
            client.insert_impacts(
                src=event.event_id,
                dst=entity.entity_id,
                impact_time=impact_time,
            )
            logger.debug(
                "linked %s -> %s (%s)",
                event.event_id,
                entity.entity_id,
                impact_time,
            )

"""
finance_mcp.ingestion.event_ingestor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Writes ParsedEvent objects into the Memgraph supply chain graph.

Pipeline
--------
ParsedEvent
    │
    ▼  upsert_event(event_id, description, severity)
Event vertex in Memgraph
    │
    ▼  insert_impacts(event_id, entity_id, impact_time)
IMPACTS edge → Company / Commodity vertex

Design
------
* Uses GraphClient for all graph interaction.
* _GraphWriter is a thin subclass that preserves the (src, dst, impact_time)
  call signature used internally by EventIngestor.
* One driver instance is opened per ingest() call and closed in a finally
  block to guarantee cleanup.
* Per-event failures are captured in IngestResult without aborting the batch.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from finance_mcp.graph.client import (
    GraphClient,
    DEFAULT_HOST,
    DEFAULT_PORT,
    AGENT_USER,
    AGENT_PASSWORD,
)
from finance_mcp.news.event_parser import ParsedEvent

logger = logging.getLogger(__name__)

_VID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


# ---------------------------------------------------------------------------
# Private graph writer — maps (src, dst) call convention to GraphClient API
# ---------------------------------------------------------------------------

class _GraphWriter(GraphClient):
    """
    Thin subclass of GraphClient that provides insert_impacts() with the
    (src, dst, impact_time) signature used by EventIngestor._ingest_one().
    """

    def insert_impacts(self, src: str, dst: str, impact_time: str) -> None:  # type: ignore[override]
        if not _VID_RE.match(src):
            raise ValueError(f"insert_impacts: invalid src VID {src!r}")
        if not _VID_RE.match(dst):
            raise ValueError(f"insert_impacts: invalid dst VID {dst!r}")
        self._run(
            "MATCH (e:Event {event_id: $event_id}) "
            "MATCH (t) WHERE "
            "  (t:Company AND t.ticker = $target) OR "
            "  (t:Commodity AND t.commodity_id = $target) "
            "MERGE (e)-[r:IMPACTS]->(t) "
            "SET r.impact_time = $impact_time",
            event_id=src, target=dst, impact_time=impact_time,
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
    Persists a batch of ParsedEvent objects into Memgraph.

    Usage::

        ingestor = EventIngestor(host="127.0.0.1", port=7687)
        result = ingestor.ingest(parsed_events)
        print(result.succeeded, "events written")
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

    def ingest_event(self, parsed_event: ParsedEvent) -> IngestResult:
        return self.ingest([parsed_event])

    def ingest(self, events: List[ParsedEvent]) -> IngestResult:
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

    def _ingest_one(self, client: _GraphWriter, event: ParsedEvent) -> None:
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

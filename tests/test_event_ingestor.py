"""
Unit tests for EventIngestor.

All tests run without a live Memgraph by patching _GraphWriter.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

from finance_mcp.ingestion.event_ingestor import EventIngestor, IngestResult, _GraphWriter
from finance_mcp.news.event_parser import ImpactedEntity, ParsedEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_id: str = "EVT_abc123def456",
    description: str = "TSMC fab shutdown",
    severity: int = 7,
    entities: list[ImpactedEntity] | None = None,
    published_at: datetime | None = None,
    source_url: str = "https://example.com/article",
) -> ParsedEvent:
    if entities is None:
        entities = [
            ImpactedEntity(entity_id="TSMC", entity_type="company", name="TSMC"),
        ]
    if published_at is None:
        published_at = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
    return ParsedEvent(
        event_id=event_id,
        description=description,
        severity=severity,
        event_type="natural_disaster",
        impacted_entities=entities,
        published_at=published_at,
        source_url=source_url,
    )


# ---------------------------------------------------------------------------
# IngestResult
# ---------------------------------------------------------------------------

class TestIngestResult:
    def test_defaults(self):
        r = IngestResult()
        assert r.total == 0
        assert r.succeeded == 0
        assert r.failed == 0
        assert r.errors == []

    def test_as_dict_keys(self):
        r = IngestResult(total=3, succeeded=2, failed=1, errors=["EVT_x: boom"])
        d = r.as_dict()
        assert set(d.keys()) == {"total", "succeeded", "failed", "errors"}

    def test_as_dict_values(self):
        r = IngestResult(total=5, succeeded=4, failed=1, errors=["EVT_y: oops"])
        d = r.as_dict()
        assert d["total"] == 5
        assert d["succeeded"] == 4
        assert d["failed"] == 1
        assert d["errors"] == ["EVT_y: oops"]

    def test_errors_is_list(self):
        r = IngestResult()
        r.errors.append("something")
        assert isinstance(r.errors, list)


# ---------------------------------------------------------------------------
# EventIngestor — unit tests (mocked graph)
# ---------------------------------------------------------------------------

class TestEventIngestorUnit:

    def _patched_ingestor(self):
        """Return (ingestor, mock_client) with _GraphWriter patched."""
        mock_client = MagicMock(spec=_GraphWriter)
        ingestor = EventIngestor(host="localhost", port=9669)
        return ingestor, mock_client

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_empty_list_returns_zero_counts(self, MockWriter):
        ingestor = EventIngestor()
        result = ingestor.ingest([])
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        MockWriter.assert_not_called()

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_single_event_calls_upsert_event(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        event = _make_event()

        ingestor = EventIngestor()
        ingestor.ingest([event])

        mock_client.upsert_event.assert_called_once_with(
            event_id=event.event_id,
            description=event.description,
            severity=event.severity,
        )

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_single_event_calls_insert_impacts_per_entity(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        entities = [
            ImpactedEntity(entity_id="TSMC", entity_type="company", name="TSMC"),
            ImpactedEntity(entity_id="SEMICONDUCTOR", entity_type="commodity", name="Semiconductors"),
        ]
        event = _make_event(entities=entities)

        ingestor = EventIngestor()
        ingestor.ingest([event])

        assert mock_client.insert_impacts.call_count == 2

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_insert_impacts_called_with_correct_args(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        published = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        event = _make_event(
            event_id="EVT_test000001",
            entities=[ImpactedEntity(entity_id="TSMC", entity_type="company", name="TSMC")],
            published_at=published,
        )

        ingestor = EventIngestor()
        ingestor.ingest([event])

        mock_client.insert_impacts.assert_called_once_with(
            src="EVT_test000001",
            dst="TSMC",
            impact_time="2026-03-09T12:00:00",
        )

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_impact_time_format(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        published = datetime(2025, 11, 22, 8, 30, 45, tzinfo=timezone.utc)
        event = _make_event(published_at=published)

        ingestor = EventIngestor()
        ingestor.ingest([event])

        _, kwargs = mock_client.insert_impacts.call_args
        assert kwargs["impact_time"] == "2025-11-22T08:30:45"

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_initialize_pool_called(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        event = _make_event()

        ingestor = EventIngestor()
        ingestor.ingest([event])

        mock_client.initialize_pool.assert_called_once()

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_close_called_after_ingest(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        event = _make_event()

        ingestor = EventIngestor()
        ingestor.ingest([event])

        mock_client.close.assert_called_once()

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_close_called_even_if_event_fails(self, MockWriter):
        mock_client = MagicMock()
        mock_client.upsert_event.side_effect = RuntimeError("graph down")
        MockWriter.return_value = mock_client
        event = _make_event()

        ingestor = EventIngestor()
        result = ingestor.ingest([event])

        mock_client.close.assert_called_once()
        assert result.failed == 1

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_result_total_matches_input_length(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        events = [_make_event(event_id=f"EVT_{i:012d}") for i in range(5)]

        ingestor = EventIngestor()
        result = ingestor.ingest(events)

        assert result.total == 5

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_all_succeed_counts(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        events = [_make_event(event_id=f"EVT_{i:012d}") for i in range(3)]

        ingestor = EventIngestor()
        result = ingestor.ingest(events)

        assert result.succeeded == 3
        assert result.failed == 0
        assert result.errors == []

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_partial_failure_counts(self, MockWriter):
        mock_client = MagicMock()
        # Second event fails
        mock_client.upsert_event.side_effect = [None, RuntimeError("boom"), None]
        MockWriter.return_value = mock_client
        events = [_make_event(event_id=f"EVT_{i:012d}") for i in range(3)]

        ingestor = EventIngestor()
        result = ingestor.ingest(events)

        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.errors) == 1

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_error_message_contains_event_id(self, MockWriter):
        mock_client = MagicMock()
        mock_client.upsert_event.side_effect = RuntimeError("connection refused")
        MockWriter.return_value = mock_client
        event = _make_event(event_id="EVT_failtest0001")

        ingestor = EventIngestor()
        result = ingestor.ingest([event])

        assert "EVT_failtest0001" in result.errors[0]

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_no_entities_upserts_event_only(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        event = _make_event(entities=[])

        ingestor = EventIngestor()
        ingestor.ingest([event])

        mock_client.upsert_event.assert_called_once()
        mock_client.insert_impacts.assert_not_called()

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_multiple_events_each_upserted(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        events = [
            _make_event(event_id="EVT_aaa000000001", severity=5),
            _make_event(event_id="EVT_bbb000000002", severity=8),
        ]

        ingestor = EventIngestor()
        ingestor.ingest(events)

        assert mock_client.upsert_event.call_count == 2
        calls = mock_client.upsert_event.call_args_list
        ids = [c.kwargs["event_id"] for c in calls]
        assert "EVT_aaa000000001" in ids
        assert "EVT_bbb000000002" in ids

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_writer_constructed_with_host_and_port(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client

        ingestor = EventIngestor(host="10.0.0.1", port=9999)
        ingestor.ingest([_make_event()])

        MockWriter.assert_called_once_with(
            host="10.0.0.1",
            port=9999,
            user=ingestor._user,
            password=ingestor._password,
        )


# ---------------------------------------------------------------------------
# ingest_event() — single-event public API
# ---------------------------------------------------------------------------

class TestIngestEvent:
    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_ingest_event_returns_ingest_result(self, MockWriter):
        MockWriter.return_value = MagicMock()
        result = EventIngestor().ingest_event(_make_event())
        assert isinstance(result, IngestResult)

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_ingest_event_total_is_one(self, MockWriter):
        MockWriter.return_value = MagicMock()
        result = EventIngestor().ingest_event(_make_event())
        assert result.total == 1

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_ingest_event_succeeded_is_one(self, MockWriter):
        MockWriter.return_value = MagicMock()
        result = EventIngestor().ingest_event(_make_event())
        assert result.succeeded == 1
        assert result.failed == 0

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_ingest_event_calls_upsert_event(self, MockWriter):
        mock_client = MagicMock()
        MockWriter.return_value = mock_client
        event = _make_event()
        EventIngestor().ingest_event(event)
        mock_client.upsert_event.assert_called_once_with(
            event_id=event.event_id,
            description=event.description,
            severity=event.severity,
        )

    @patch("finance_mcp.ingestion.event_ingestor._GraphWriter")
    def test_ingest_event_failure_captured(self, MockWriter):
        mock_client = MagicMock()
        mock_client.upsert_event.side_effect = RuntimeError("db error")
        MockWriter.return_value = mock_client
        result = EventIngestor().ingest_event(_make_event())
        assert result.failed == 1
        assert result.succeeded == 0
        assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# _GraphWriter unit test (import only — no live graph needed)
# ---------------------------------------------------------------------------

class TestGraphWriter:
    def test_is_subclass_of_graph_client(self):
        from finance_mcp.graph.client import GraphClient
        assert issubclass(_GraphWriter, GraphClient)

    def test_has_insert_impacts_method(self):
        assert callable(getattr(_GraphWriter, "insert_impacts", None))


# ---------------------------------------------------------------------------
# Integration smoke test (requires live Memgraph)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ingest_live_event():
    """Writes one event + one IMPACTS edge to Memgraph and verifies."""
    from finance_mcp.graph.client import GraphClient

    event = _make_event(
        event_id="EVT_integtest0001",
        description="Integration test event — safe to delete",
        severity=1,
        entities=[
            ImpactedEntity(entity_id="TSMC", entity_type="company", name="TSMC"),
        ],
    )

    ingestor = EventIngestor()
    result = ingestor.ingest([event])

    assert result.succeeded == 1, f"Ingest failed: {result.errors}"

    # Verify the event vertex was written
    with GraphClient() as client:
        ev = client.fetch_event("EVT_integtest0001")
        assert ev, "Expect Event vertex to exist after ingest"
        # Cleanup
        client._run(
            "MATCH (e:Event {event_id: $id}) DETACH DELETE e",
            id="EVT_integtest0001",
        )

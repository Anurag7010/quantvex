#!/usr/bin/env python3
"""
verify_ingest.py
~~~~~~~~~~~~~~~~
Step 4 verification: insert a test event via EventIngestor and confirm
the Event vertex and IMPACTS edges appear in NebulaGraph.

Run with:
    PYTHONPATH=src python tests/verify_ingest.py

Requires a live NebulaGraph instance on 127.0.0.1:9669.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

# Add src to path so imports work when run directly
sys.path.insert(0, "src")

from finance_mcp.graph.client import SecureGraphClient
from finance_mcp.ingestion.event_ingestor import EventIngestor
from finance_mcp.news.event_parser import ImpactedEntity, ParsedEvent

# ---------------------------------------------------------------------------
# Test fixture
# ---------------------------------------------------------------------------

TEST_EVENT_ID = "EVT_verify00001"

TEST_EVENT = ParsedEvent(
    event_id=TEST_EVENT_ID,
    description="Verification test: TSMC fab shutdown due to earthquake",
    severity=8,
    event_type="natural_disaster",
    impacted_entities=[
        ImpactedEntity(entity_id="TSMC",        entity_type="company",   name="TSMC"),
        ImpactedEntity(entity_id="SEMICONDUCTOR", entity_type="commodity", name="Semiconductors"),
    ],
    published_at=datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc),
    source_url="https://example.com/verify-test",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  {PASS}  {label}")
    else:
        marker = f"  {FAIL}  {label}"
        if detail:
            marker += f"\n         {detail}"
        print(marker)
        _failures.append(label)


# ---------------------------------------------------------------------------
# Step 1 — Insert prerequisite vertices then the test event
# ---------------------------------------------------------------------------

def step1_insert() -> None:
    print("\n[Step 1] Insert test event via EventIngestor.ingest_event()")

    # Ensure prerequisite Company and Commodity vertices exist so the
    # IMPACTS traversal can resolve them by label.
    with SecureGraphClient() as client:
        client.insert_company("TSMC", "Taiwan Semiconductor Manufacturing Co.", "Technology")
        client.insert_commodity("SEMICONDUCTOR", "Semiconductors", "Electronic Components")

    ingestor = EventIngestor()
    result = ingestor.ingest_event(TEST_EVENT)

    check("ingest_event() returned IngestResult", result is not None)
    check("total == 1", result.total == 1, f"got {result.total}")
    check("succeeded == 1", result.succeeded == 1,
          f"got {result.succeeded}; errors: {result.errors}")
    check("failed == 0", result.failed == 0, f"errors: {result.errors}")


# ---------------------------------------------------------------------------
# Step 2 — Verify Event vertex exists in graph
# ---------------------------------------------------------------------------

def step2_verify_event_vertex() -> None:
    print("\n[Step 2] Verify Event vertex in NebulaGraph")
    with SecureGraphClient() as client:
        rs = client.fetch_event(TEST_EVENT_ID)

    check("fetch_event() succeeded",  rs.is_succeeded())
    check("Event vertex exists (non-empty result)", not rs.is_empty(),
          "Expected 1 row, got empty ResultSet")

    if not rs.is_empty():
        row = rs.row_values(0)
        props = row[0].as_map()
        desc_val  = props.get("description", None)
        sev_val   = props.get("severity",    None)
        desc_str  = desc_val.as_string()  if desc_val  else ""
        sev_int   = sev_val.as_int()      if sev_val   else -1

        check("description stored correctly",
              desc_str == TEST_EVENT.description,
              f"got {desc_str!r}")
        check("severity stored correctly",
              sev_int == TEST_EVENT.severity,
              f"got {sev_int}")


# ---------------------------------------------------------------------------
# Step 3 — Verify IMPACTS edges
# ---------------------------------------------------------------------------

def step3_verify_impacts_edges() -> None:
    print("\n[Step 3] Verify IMPACTS edges from event to entities")
    with SecureGraphClient() as client:
        rs = client.get_events_impacting_company("TSMC")

    check("get_events_impacting_company() succeeded", rs.is_succeeded())

    event_ids: list[str] = []
    if not rs.is_empty():
        for i in range(rs.row_size()):
            row = rs.row_values(i)
            # Column 0 is id(s) — Event vertex ID
            event_ids.append(row[0].as_string())

    check(
        f"IMPACTS edge {TEST_EVENT_ID} → TSMC present",
        TEST_EVENT_ID in event_ids,
        f"found event IDs: {event_ids[:10]}",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  Finance MCP — Phase 3 Graph Ingest Verification")
    print("=" * 60)

    try:
        step1_insert()
        step2_verify_event_vertex()
        step3_verify_impacts_edges()
    except Exception as exc:
        print(f"\n  {FAIL}  Unexpected error: {exc}")
        _failures.append(str(exc))

    print()
    if _failures:
        print(f"RESULT: {len(_failures)} check(s) failed:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("RESULT: All checks passed — graph writes verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()

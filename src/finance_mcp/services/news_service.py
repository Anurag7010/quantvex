from __future__ import annotations

from typing import Any

from finance_mcp.graph.client import GraphClient
from finance_mcp.ingestion.pipeline import run_news_ingestion_pipeline
from mcp_server.config import get_settings


async def run_news_pipeline(
    query: str,
    ticker: str | None = None,
    limit: int = 5,
    max_hops: int = 2,
) -> dict[str, Any]:
    """Run news ingestion plus graph cascade without using invoke handlers."""
    settings = get_settings()
    pipeline_result = await run_news_ingestion_pipeline(
        query=query,
        limit=limit,
        memgraph_host=settings.memgraph_host,
        memgraph_port=settings.memgraph_port,
    )
    company_entities: dict[str, str] = {}
    for event in pipeline_result.parsed_events:
        for entity in event.impacted_entities:
            if entity.entity_type == "company":
                company_entities[entity.entity_id] = entity.name

    if ticker:
        company_entities.setdefault(ticker.strip().upper(), ticker.strip().upper())

    cascade_count = 0
    with GraphClient(host=settings.memgraph_host, port=settings.memgraph_port) as client:
        for entity_ticker in company_entities:
            cascade_count += len(client.trace_impact(entity_ticker, max_hops))

    return {
        "success": True,
        "data": {
            "events_found": pipeline_result.events_parsed,
            "total_cascade_companies": cascade_count,
        },
    }

"""
finance_mcp.ingestion.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Orchestrates the full Phase 3 ingestion pipeline:

    NewsClient  →  EventParser  →  EventIngestor  →  NebulaGraph

Primary entry point::

    from finance_mcp.ingestion.pipeline import run_news_ingestion_pipeline

    result = await run_news_ingestion_pipeline("semiconductor disruption", limit=10)
    print(result.succeeded, "events written to graph")

Design
------
* Async — NewsClient.fetch_market_news() is an httpx coroutine.
* All three stages are independent error domains: an API failure raises
  immediately; parser failures are skipped (logged); ingestor failures
  are captured in IngestResult.errors without aborting the batch.
* Config (NebulaGraph host/port, NewsAPI key) is read from MCP settings
  so that the same .env file controls the whole stack.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from finance_mcp.ingestion.event_ingestor import EventIngestor, IngestResult
from finance_mcp.news.event_parser import EventParser, ParsedEvent
from finance_mcp.news.news_client import NewsArticle, NewsClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PipelineResult — richer summary that wraps IngestResult
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    End-to-end summary returned by run_news_ingestion_pipeline().

    Attributes
    ----------
    query          : str              — the search query used
    articles_fetched : int            — articles returned by NewsAPI
    events_parsed  : int              — articles that produced a ParsedEvent
    ingest_result  : IngestResult     — graph-write statistics
    parsed_events  : List[ParsedEvent] — events that were passed to ingestor
    """
    query: str
    articles_fetched: int = 0
    events_parsed: int = 0
    ingest_result: IngestResult = field(default_factory=IngestResult)
    parsed_events: List[ParsedEvent] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return self.ingest_result.succeeded

    @property
    def failed(self) -> int:
        return self.ingest_result.failed

    @property
    def errors(self) -> List[str]:
        return self.ingest_result.errors

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "articles_fetched": self.articles_fetched,
            "events_parsed": self.events_parsed,
            "graph_writes": self.ingest_result.as_dict(),
        }


# ---------------------------------------------------------------------------
# Public orchestration function
# ---------------------------------------------------------------------------

async def run_news_ingestion_pipeline(
    query: str,
    limit: int = 10,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    news_api_key: Optional[str] = None,
    nebula_host: Optional[str] = None,
    nebula_port: Optional[int] = None,
) -> PipelineResult:
    """
    Fetch news, parse disruption events and write them to NebulaGraph.

    Pipeline
    --------
    1. NewsClient.fetch_market_news(query, limit) → List[NewsArticle]
    2. EventParser.parse_articles(articles)       → List[ParsedEvent]
    3. EventIngestor.ingest(events)               → IngestResult

    Parameters
    ----------
    query        : str         — NewsAPI search terms, e.g. "semiconductor"
    limit        : int         — max articles to fetch (1–100)
    from_date    : str | None  — ISO-8601 lower date bound
    to_date      : str | None  — ISO-8601 upper date bound
    news_api_key : str | None  — override the key from settings
    nebula_host  : str | None  — NebulaGraph host (default: read from settings/env)
    nebula_port  : int | None  — NebulaGraph port (default: read from settings/env)

    Returns
    -------
    PipelineResult
        Full statistics for each stage.

    Raises
    ------
    ValueError
        When query is empty or limit is invalid.
    httpx.HTTPStatusError | RuntimeError
        When NewsAPI returns an error.  Propagated to the caller so that
        the upstream can decide whether to retry.
    """
    result = PipelineResult(query=query)

    # ------------------------------------------------------------------
    # Stage 1 — Fetch news
    # ------------------------------------------------------------------
    logger.info("pipeline: fetching news  query=%r limit=%d", query, limit)
    news_client = NewsClient(api_key=news_api_key)
    articles: List[NewsArticle] = await news_client.fetch_market_news(
        query=query,
        limit=limit,
        from_date=from_date,
        to_date=to_date,
    )
    result.articles_fetched = len(articles)
    logger.info("pipeline: fetched %d articles", result.articles_fetched)

    if not articles:
        logger.info("pipeline: no articles from NewsAPI, trying RSS fallback")
        articles = await news_client.fetch_articles_fallback(query)
        result.articles_fetched = len(articles)
        logger.info("pipeline: RSS fallback returned %d articles", result.articles_fetched)

    if not articles:
        logger.info("pipeline: no articles returned, exiting early")
        return result

    # ------------------------------------------------------------------
    # Stage 2 — Parse events
    # ------------------------------------------------------------------
    parser = EventParser()
    parsed: List[ParsedEvent] = parser.parse_articles(articles)
    result.events_parsed = len(parsed)
    result.parsed_events = parsed
    logger.info(
        "pipeline: parsed %d/%d articles into events",
        result.events_parsed,
        result.articles_fetched,
    )

    if not parsed:
        logger.info("pipeline: no disruptive events detected, exiting early")
        return result

    # ------------------------------------------------------------------
    # Stage 3 — Ingest into graph
    # Resolve host/port: explicit args → env vars → client defaults
    # ------------------------------------------------------------------
    from finance_mcp.graph.client import DEFAULT_HOST, DEFAULT_PORT
    resolved_host = nebula_host if nebula_host is not None else DEFAULT_HOST
    resolved_port = nebula_port if nebula_port is not None else DEFAULT_PORT
    ingestor = EventIngestor(host=resolved_host, port=resolved_port)
    result.ingest_result = ingestor.ingest(parsed)
    logger.info(
        "pipeline: graph writes  ok=%d failed=%d",
        result.ingest_result.succeeded,
        result.ingest_result.failed,
    )

    return result

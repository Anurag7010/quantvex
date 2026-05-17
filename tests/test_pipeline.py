"""
Unit tests for run_news_ingestion_pipeline() and PipelineResult.

All tests mock NewsClient, EventParser, and EventIngestor so that the
pipeline logic can be verified without network or database access.
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from finance_mcp.ingestion.event_ingestor import IngestResult
from finance_mcp.ingestion.pipeline import PipelineResult, run_news_ingestion_pipeline
from finance_mcp.news.event_parser import ImpactedEntity, ParsedEvent
from finance_mcp.news.news_client import NewsArticle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_article(title="TSMC fab shutdown after earthquake", i=0) -> NewsArticle:
    return NewsArticle(
        title=title,
        description="Semiconductor supply disruption expected",
        url=f"https://example.com/article-{i}",
        published_at=datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc),
        source_name="Reuters",
        query="semiconductor",
    )


def _make_event(i=0) -> ParsedEvent:
    return ParsedEvent(
        event_id=f"EVT_{i:012d}",
        description="TSMC production halted",
        severity=7,
        event_type="natural_disaster",
        impacted_entities=[
            ImpactedEntity(entity_id="TSMC", entity_type="company", name="TSMC"),
        ],
        published_at=datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc),
        source_url=f"https://example.com/article-{i}",
    )


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------

class TestPipelineResult:
    def test_defaults(self):
        r = PipelineResult(query="test")
        assert r.articles_fetched == 0
        assert r.events_parsed == 0
        assert r.succeeded == 0
        assert r.failed == 0
        assert r.errors == []

    def test_succeeded_delegates_to_ingest_result(self):
        r = PipelineResult(query="test", ingest_result=IngestResult(succeeded=5))
        assert r.succeeded == 5

    def test_failed_delegates_to_ingest_result(self):
        r = PipelineResult(query="test", ingest_result=IngestResult(failed=2))
        assert r.failed == 2

    def test_errors_delegates_to_ingest_result(self):
        r = PipelineResult(query="test", ingest_result=IngestResult(errors=["oops"]))
        assert r.errors == ["oops"]

    def test_as_dict_keys(self):
        r = PipelineResult(query="test")
        d = r.as_dict()
        assert set(d.keys()) == {"query", "articles_fetched", "events_parsed", "graph_writes"}

    def test_as_dict_query(self):
        r = PipelineResult(query="lithium")
        assert r.as_dict()["query"] == "lithium"

    def test_as_dict_graph_writes_is_dict(self):
        r = PipelineResult(query="test")
        assert isinstance(r.as_dict()["graph_writes"], dict)


# ---------------------------------------------------------------------------
# Pipeline — happy path
# ---------------------------------------------------------------------------

class TestPipelineHappyPath:

    @pytest.fixture
    def _articles(self):
        return [_make_article(i=i) for i in range(3)]

    @pytest.fixture
    def _events(self):
        return [_make_event(i=i) for i in range(2)]

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_returns_pipeline_result(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult(total=2, succeeded=2)

        result = await run_news_ingestion_pipeline("semiconductor", limit=5)

        assert isinstance(result, PipelineResult)

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_articles_fetched_count(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult(total=2, succeeded=2)

        result = await run_news_ingestion_pipeline("semiconductor")
        assert result.articles_fetched == 3

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_events_parsed_count(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult(total=2, succeeded=2)

        result = await run_news_ingestion_pipeline("semiconductor")
        assert result.events_parsed == 2

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_succeeded_count(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult(total=2, succeeded=2, failed=0)

        result = await run_news_ingestion_pipeline("semiconductor")
        assert result.succeeded == 2
        assert result.failed == 0

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_query_preserved_in_result(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult()

        result = await run_news_ingestion_pipeline("lithium supply")
        assert result.query == "lithium supply"

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_parsed_events_stored(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult()

        result = await run_news_ingestion_pipeline("semiconductor")
        assert result.parsed_events == _events

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_news_client_receives_query_and_limit(self, MockNews, MockParser, MockIngestor, _articles, _events):
        mock_fetch = AsyncMock(return_value=_articles)
        MockNews.return_value.fetch_market_news = mock_fetch
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult()

        await run_news_ingestion_pipeline("rare earth", limit=7)
        mock_fetch.assert_called_once_with(query="rare earth", limit=7, from_date=None, to_date=None)

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_parser_receives_all_articles(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        mock_parse = MagicMock(return_value=_events)
        MockParser.return_value.parse_articles = mock_parse
        MockIngestor.return_value.ingest.return_value = IngestResult()

        await run_news_ingestion_pipeline("semiconductor")
        mock_parse.assert_called_once_with(_articles)

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_ingestor_receives_parsed_events(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        mock_ingest = MagicMock(return_value=IngestResult())
        MockIngestor.return_value.ingest = mock_ingest

        await run_news_ingestion_pipeline("semiconductor")
        mock_ingest.assert_called_once_with(_events)

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_ingestor_constructed_with_nebula_params(self, MockNews, MockParser, MockIngestor, _articles, _events):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=_articles)
        MockParser.return_value.parse_articles.return_value = _events
        MockIngestor.return_value.ingest.return_value = IngestResult()

        await run_news_ingestion_pipeline("semiconductor", nebula_host="10.0.0.1", nebula_port=9999)
        MockIngestor.assert_called_once_with(host="10.0.0.1", port=9999)


# ---------------------------------------------------------------------------
# Pipeline — early exit paths
# ---------------------------------------------------------------------------

class TestPipelineEarlyExit:

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_no_articles_returns_zero_events(self, MockNews, MockParser, MockIngestor):
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=[])
        MockNews.return_value.fetch_articles_fallback = AsyncMock(return_value=[])

        result = await run_news_ingestion_pipeline("obscure query")

        assert result.articles_fetched == 0
        assert result.events_parsed == 0
        assert result.succeeded == 0
        MockParser.return_value.parse_articles.assert_not_called()
        MockIngestor.return_value.ingest.assert_not_called()

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_no_disruptive_events_skips_ingest(self, MockNews, MockParser, MockIngestor):
        articles = [_make_article()]
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=articles)
        MockParser.return_value.parse_articles.return_value = []  # nothing disruptive

        result = await run_news_ingestion_pipeline("earnings report")

        assert result.articles_fetched == 1
        assert result.events_parsed == 0
        MockIngestor.return_value.ingest.assert_not_called()


# ---------------------------------------------------------------------------
# Pipeline — error handling
# ---------------------------------------------------------------------------

class TestPipelineErrorHandling:

    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_api_failure_propagates(self, MockNews):
        MockNews.return_value.fetch_market_news = AsyncMock(
            side_effect=RuntimeError("NewsAPI rate limit exceeded")
        )
        with pytest.raises(RuntimeError, match="rate limit"):
            await run_news_ingestion_pipeline("semiconductor")

    @patch("finance_mcp.ingestion.pipeline.EventIngestor")
    @patch("finance_mcp.ingestion.pipeline.EventParser")
    @patch("finance_mcp.ingestion.pipeline.NewsClient")
    async def test_partial_graph_failure_captured(self, MockNews, MockParser, MockIngestor):
        articles = [_make_article(i=i) for i in range(3)]
        events = [_make_event(i=i) for i in range(3)]
        MockNews.return_value.fetch_market_news = AsyncMock(return_value=articles)
        MockParser.return_value.parse_articles.return_value = events
        MockIngestor.return_value.ingest.return_value = IngestResult(
            total=3, succeeded=2, failed=1, errors=["EVT_000000000002: db error"]
        )

        result = await run_news_ingestion_pipeline("semiconductor")
        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.errors) == 1

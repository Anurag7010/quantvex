"""
Phase 3 — EventParser tests.

Static unit tests (no network, no API key needed):
    PYTHONPATH=src .venv/bin/python3.11 -m pytest tests/test_event_parser.py -v

Live integration test (requires NEWS_API_KEY in env):
    NEWS_API_KEY=<key> PYTHONPATH=src .venv/bin/python3.11 -m pytest \
        tests/test_event_parser.py -v -m live
"""
from __future__ import annotations

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from finance_mcp.news.event_parser import EventParser, ParsedEvent, ImpactedEntity


# ---------------------------------------------------------------------------
# Minimal NewsArticle stub — avoids importing NewsClient (no API key needed)
# ---------------------------------------------------------------------------

@dataclass
class _Article:
    title: str
    description: str
    url: str = "https://example.com/article"
    published_at: datetime = None
    source_name: str = "Test Source"
    query: str = ""

    def __post_init__(self):
        if self.published_at is None:
            self.published_at = datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def parser():
    return EventParser()


# ---------------------------------------------------------------------------
# Severity rules
# ---------------------------------------------------------------------------

class TestDisruptionScoring:

    def test_earthquake_severity_8(self, parser):
        a = _Article("Earthquake disrupts TSMC semiconductor production", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.severity >= 8

    def test_strike_severity_7(self, parser):
        a = _Article("Workers strike at lithium mine halts output", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.severity >= 7

    def test_shortage_severity_6(self, parser):
        a = _Article("Global chip shortage worsens amid demand surge", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.severity >= 6

    def test_sanctions_severity_8(self, parser):
        a = _Article("US sanctions on semiconductor exports announced", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.severity >= 8

    def test_severity_capped_at_10(self, parser):
        a = _Article(
            "Earthquake tsunami war sanctions embargo factory explosion strike shortage",
            "production halt disruption outage shutdown closure"
        )
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.severity == 10

    def test_no_disruption_returns_none(self, parser):
        a = _Article("Apple announces new iPhone SE model", "Great features expected")
        result = parser.parse_news_article(a)
        assert result is None

    def test_event_type_set_by_first_match(self, parser):
        # earthquake matches first → natural_disaster
        a = _Article("Earthquake causes factory shutdown near TSMC", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.event_type == "natural_disaster"

    def test_labour_event_type(self, parser):
        a = _Article("Lithium mine workers go on strike", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.event_type == "labour"

    def test_supply_chain_event_type(self, parser):
        a = _Article("Semiconductor shortage hits auto industry", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.event_type == "supply_chain"


# ---------------------------------------------------------------------------
# Company entity recognition
# ---------------------------------------------------------------------------

class TestCompanyRecognition:

    def test_tsmc_detected(self, parser):
        a = _Article("TSMC factory fire disrupts chip production", "")
        e = parser.parse_news_article(a)
        assert e is not None
        ids = {ent.entity_id for ent in e.impacted_entities}
        assert "TSMC" in ids

    def test_nvidia_detected(self, parser):
        a = _Article("NVIDIA faces shortage of advanced wafers", "")
        e = parser.parse_news_article(a)
        assert e is not None
        ids = {ent.entity_id for ent in e.impacted_entities}
        assert "NVDA" in ids

    def test_apple_detected(self, parser):
        a = _Article("Apple production disrupted by Taiwan earthquake", "")
        e = parser.parse_news_article(a)
        assert e is not None
        ids = {ent.entity_id for ent in e.impacted_entities}
        assert "AAPL" in ids

    def test_no_duplicate_entities(self, parser):
        a = _Article("TSMC TSMC TSMC earthquake outage shutdown", "TSMC TSMC")
        e = parser.parse_news_article(a)
        assert e is not None
        company_ids = [ent.entity_id for ent in e.impacted_entities if ent.entity_id == "TSMC"]
        assert len(company_ids) == 1

    def test_entity_type_is_company(self, parser):
        a = _Article("TSMC earthquake disrupts production", "")
        e = parser.parse_news_article(a)
        assert e is not None
        tsmc = next(ent for ent in e.impacted_entities if ent.entity_id == "TSMC")
        assert tsmc.entity_type == "company"


# ---------------------------------------------------------------------------
# Commodity entity recognition
# ---------------------------------------------------------------------------

class TestCommodityRecognition:

    def test_lithium_detected(self, parser):
        a = _Article("Lithium mine strike halts production", "")
        e = parser.parse_news_article(a)
        assert e is not None
        ids = {ent.entity_id for ent in e.impacted_entities}
        assert "LITHIUM" in ids

    def test_semiconductor_commodity_detected(self, parser):
        a = _Article("Chip shortage disrupts automotive supply chain", "")
        e = parser.parse_news_article(a)
        assert e is not None
        ids = {ent.entity_id for ent in e.impacted_entities}
        assert "SEMICONDUCTOR" in ids

    def test_rare_earth_detected(self, parser):
        a = _Article("China exports ban on rare earths shocks market", "")
        e = parser.parse_news_article(a)
        assert e is not None
        ids = {ent.entity_id for ent in e.impacted_entities}
        assert "RARE_EARTH" in ids

    def test_entity_type_is_commodity(self, parser):
        a = _Article("Lithium mine strike", "")
        e = parser.parse_news_article(a)
        assert e is not None
        lit = next((ent for ent in e.impacted_entities if ent.entity_id == "LITHIUM"), None)
        assert lit is not None
        assert lit.entity_type == "commodity"


# ---------------------------------------------------------------------------
# ParsedEvent structure
# ---------------------------------------------------------------------------

class TestParsedEventStructure:

    def test_event_id_deterministic(self, parser):
        a = _Article("TSMC earthquake disrupts chip production", "desc",
                     url="https://example.com/tsmc-quake")
        e1 = parser.parse_news_article(a)
        e2 = parser.parse_news_article(a)
        assert e1 is not None and e2 is not None
        assert e1.event_id == e2.event_id

    def test_event_id_starts_with_EVT(self, parser):
        a = _Article("TSMC earthquake halts production", "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.event_id.startswith("EVT_")

    def test_description_max_200_chars(self, parser):
        long_title = "A" * 300 + " earthquake disrupts supply chain"
        a = _Article(long_title, "")
        e = parser.parse_news_article(a)
        assert e is not None
        assert len(e.description) <= 200

    def test_as_dict_serialisable(self, parser):
        import json
        a = _Article("Lithium mine strike halts cobalt mining output", "miners walked out")
        e = parser.parse_news_article(a)
        assert e is not None
        d = e.as_dict()
        json.dumps(d)  # must not raise
        assert "event_id" in d
        assert "severity" in d
        assert "impacted_entities" in d

    def test_published_at_preserved(self, parser):
        ts = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        a = _Article("TSMC factory fire disrupts production", "", published_at=ts)
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.published_at == ts

    def test_source_url_preserved(self, parser):
        a = _Article("TSMC earthquake halts production", "",
                     url="https://reuters.com/tsmc-outage")
        e = parser.parse_news_article(a)
        assert e is not None
        assert e.source_url == "https://reuters.com/tsmc-outage"


# ---------------------------------------------------------------------------
# parse_articles batch method
# ---------------------------------------------------------------------------

class TestParseArticles:

    def test_filters_non_disruptive(self, parser):
        articles = [
            _Article("Apple announces new iPhone SE", "Great features"),
            _Article("TSMC earthquake disrupts chip production", ""),
            _Article("Quarterly earnings beat expectations", ""),
            _Article("Lithium mine strike halts output", ""),
        ]
        events = parser.parse_articles(articles)
        assert len(events) == 2

    def test_empty_input(self, parser):
        assert parser.parse_articles([]) == []

    def test_all_non_disruptive(self, parser):
        articles = [
            _Article("New product launch", ""),
            _Article("CEO interview published", ""),
        ]
        assert parser.parse_articles(articles) == []


# ---------------------------------------------------------------------------
# Live integration test (optional — skip if no API key)
# ---------------------------------------------------------------------------

@pytest.mark.live
def test_live_parse_semiconductor_news():
    """Fetch real semiconductor news and parse events — requires NEWS_API_KEY."""
    import asyncio
    import os

    key = os.environ.get("NEWS_API_KEY", "").strip()
    if not key:
        pytest.skip("NEWS_API_KEY not set")

    from finance_mcp.news.news_client import NewsClient

    async def _run():
        client = NewsClient(api_key=key)
        articles = await client.fetch_semiconductor_news(limit=10)
        return articles

    articles = asyncio.run(_run())
    parser = EventParser()
    events = parser.parse_articles(articles)

    print(f"\nFetched {len(articles)} articles, parsed {len(events)} events")
    for ev in events:
        entity_names = [e.name for e in ev.impacted_entities]
        print(f"  [{ev.severity}/10] {ev.description[:80]}")
        print(f"    entities: {entity_names}")

    # We can't guarantee disruptions in any given week, so just assert structure
    for ev in events:
        assert ev.event_id.startswith("EVT_")
        assert 1 <= ev.severity <= 10
        assert len(ev.description) <= 200

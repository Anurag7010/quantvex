"""
Step 12 - Multi-query pipeline test.
Run: PYTHONPATH=src .venv/bin/python3.11 tests/step12_multi_query.py
"""
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, "src")

try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from finance_mcp.ingestion.pipeline import run_news_ingestion_pipeline
from finance_mcp.graph.client import SecureGraphClient

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

QUERIES = [
    ("Russia Ukraine war energy disruption",    "SHEL",  "Energy shock — Russia/Ukraine"),
    ("semiconductor shortage Taiwan chip",       "TSMC",  "Chip shortage — Taiwan"),
    ("lithium supply chain disruption battery",  "TSLA",  "Lithium disruption — EV"),
    ("oil supply shock Middle East OPEC",        "XOM",   "Oil shock — Middle East"),
]


async def run_all():
    if not NEWS_API_KEY:
        print("ERROR: NEWS_API_KEY not set in .env")
        sys.exit(1)

    print("=" * 65)
    print("  STEP 12 — Multi-Query Supply Chain Disruption Test")
    print("=" * 65)

    for query, ticker, label in QUERIES:
        print(f"\n{'─'*65}")
        print(f"  QUERY : {label}")
        print(f"  Topic : {query}")
        print(f"  Ticker: {ticker}")
        print("─" * 65)

        # 1. Run news ingestion pipeline
        result = await run_news_ingestion_pipeline(
            query=query,
            limit=5,
            news_api_key=NEWS_API_KEY,
            nebula_host="127.0.0.1",
            nebula_port=9669,
        )
        print(f"  Pipeline  → fetched={result.articles_fetched}  "
              f"parsed={result.events_parsed}  "
              f"written={result.succeeded}  "
              f"failed={result.failed}")

        # 2. Run trace_impact to find downstream exposure
        with SecureGraphClient() as c:
            impacts = c.trace_impact(target_ticker=ticker, max_hops=3)

        print(f"  trace_impact({ticker}, 3 hops) → {len(impacts)} companies exposed:")
        for company in impacts:
            print(f"    • {company['ticker']:6s} {company['name']} [{company['sector']}]")
        if not impacts:
            print("    (no downstream companies linked yet)")

    print(f"\n{'='*65}")
    print("  All 4 scenarios completed successfully.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_all())

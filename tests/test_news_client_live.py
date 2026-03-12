"""
Phase 3 — live NewsClient smoke test.

Run:
    PYTHONPATH=src .venv/bin/python3.11 tests/test_news_client_live.py

Requires NEWS_API_KEY to be set in .env.
"""
import asyncio
import pathlib
import sys

# Load .env manually so the test can be run standalone
try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on env already being set

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from finance_mcp.news.news_client import NewsClient


def _print_articles(label: str, articles):
    print(f"\n{'='*60}")
    print(f"  {label}  ({len(articles)} articles)")
    print('='*60)
    if not articles:
        print("  (no articles returned)")
        return
    for i, a in enumerate(articles, 1):
        print(f"\n  [{i}] {a.title}")
        print(f"      Source : {a.source_name}")
        print(f"      Date   : {a.published_at.strftime('%Y-%m-%d %H:%M UTC')}")
        desc = a.description[:120] + "..." if len(a.description or "") > 120 else a.description
        print(f"      Desc   : {desc or '(none)'}")


async def main():
    # Read key directly from env to validate it loaded
    import os
    key = os.environ.get("NEWS_API_KEY", "").strip()
    if not key:
        print("ERROR: NEWS_API_KEY not found in environment. Check your .env file.")
        sys.exit(1)
    print(f"NEWS_API_KEY loaded OK (length={len(key)})")

    client = NewsClient(api_key=key)

    print("\nFetching semiconductor news...")
    semi = await client.fetch_semiconductor_news(limit=3)
    _print_articles("Semiconductor News", semi)

    print("\nFetching lithium news...")
    lithium = await client.fetch_lithium_news(limit=3)
    _print_articles("Lithium News", lithium)

    print("\n\nSmoke test PASSED")


if __name__ == "__main__":
    asyncio.run(main())

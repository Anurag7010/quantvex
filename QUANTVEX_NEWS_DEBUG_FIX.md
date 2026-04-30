# QuantVex — News Fetch Debug & Fix

## Step 1 — Diagnose exactly what's failing

Run this first:

```bash
python3 -c "
import asyncio, aiohttp, os
from dotenv import load_dotenv
load_dotenv()

async def test():
    key = os.getenv('NEWSDATA_API_KEY')
    print(f'Key present: {bool(key)}, starts with: {key[:8] if key else None}')

    queries = [
        'NVIDIA export controls China',
        'NVIDIA chips',
        'semiconductor export',
        'tariffs markets',
    ]
    async with aiohttp.ClientSession() as session:
        for q in queries:
            url = 'https://newsdata.io/api/1/news'
            params = {'apikey': key, 'q': q, 'language': 'en', 'size': 3}
            async with session.get(url, params=params) as r:
                data = await r.json()
                count = len(data.get('results', []))
                status = data.get('status')
                print(f'Query [{q}]: status={status}, articles={count}')
                if count:
                    print(f'  Sample: {data[\"results\"][0][\"title\"][:70]}')

asyncio.run(test())
"
```

This tells you exactly which queries return results and which don't.

---

## Step 2 — Replace fetch logic with a working implementation

The issue: `category=business,technology` filter + specific queries = NewsData.io returns nothing because category + keyword filtering is too restrictive on free tier.

**Fix: remove the category filter, use `latest` endpoint instead of `news` endpoint for broader coverage.**

Replace `finance_mcp/news_client.py` `fetch_articles` method:

```python
async def fetch_articles(self, query: str, max_results: int = 10) -> list[NewsArticle]:
    """
    Strategy: try 3 progressively broader queries until we get results.
    """
    words = query.split()

    # Build query ladder: specific → medium → broad
    query_ladder = [
        query,                                    # Full query
        " ".join(words[:3]) if len(words) > 3 else query,  # First 3 words
        " ".join(words[:2]) if len(words) > 2 else words[0],  # First 2 words
    ]
    # Deduplicate
    query_ladder = list(dict.fromkeys(query_ladder))

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=15)
    ) as session:
        for q in query_ladder:
            articles = await self._fetch_single(session, q, max_results)
            if articles:
                return articles

        # Final fallback: latest financial news (no keyword filter)
        return await self._fetch_single(session, "stock market finance", max_results)

async def _fetch_single(
    self, session: aiohttp.ClientSession, query: str, size: int
) -> list[NewsArticle]:
    params = {
        "apikey": self.api_key,
        "q": query,
        "language": "en",
        # NO category filter — too restrictive on free tier
        "size": min(size, 10),
        "prioritydomain": "top",   # top-tier sources only
    }
    try:
        async with session.get(self.base_url, params=params) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            results = data.get("results", [])
            articles = []
            for item in results:
                if not item.get("title"):
                    continue
                article_id = hashlib.md5(
                    (item.get("link", "") + item.get("title", "")).encode()
                ).hexdigest()[:12]
                articles.append(NewsArticle(
                    title=item["title"],
                    url=item.get("link", ""),
                    source=item.get("source_id", "unknown"),
                    published_at=item.get("pubDate", ""),
                    content=item.get("description") or item["title"],
                    article_id=article_id
                ))
            return articles
    except Exception:
        return []
```

---

## Step 3 — Also fix the chat agent to pass cleaner queries

The agent sends verbose queries like "NVIDIA's export controls to China semiconductor industry impact" — too many words, NewsData.io matches nothing.

In `mcp_server/chat_agent.py`, update the `analyze_news_impact` tool description:

```python
"description": (
    "Fetch real-time news and analyze market impact. "
    "ALWAYS use for any question about current events, news, or recent developments. "
    "Keep the query SHORT — 2 to 4 keywords maximum. "
    "Good: 'NVIDIA export controls', 'Fed rate decision', 'oil supply OPEC'. "
    "Bad: 'what is happening with NVIDIA chip export controls to China and its impact'. "
    "Short queries return more results."
),
```

---

## Step 4 — Verify

```bash
# Direct API test
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from finance_mcp.news_client import NewsClient
async def t():
    c = NewsClient()
    arts = await c.fetch_articles('NVIDIA export controls')
    print(f'Articles: {len(arts)}')
    for a in arts[:3]:
        print(f'  [{a.published_at[:10]}] {a.source}: {a.title[:70]}')
asyncio.run(t())
"
# Must show 3+ articles with real titles
```

Then ask in chat: **"NVIDIA export controls China"** (short query)
Response must cite actual article titles and dates.

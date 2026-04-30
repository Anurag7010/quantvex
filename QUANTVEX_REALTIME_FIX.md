# QuantVex — Real-Time Data & News Fix (Final)

## Problem 1: Dashboard Not Fetching Real-Time Data

### Root Cause Diagnosis
Before writing any code, open `DashboardPage.tsx` and check:
1. Is `fetchIndianMarket()` actually called in a `useEffect`?
2. Are the Yahoo Finance / open.er-api.com URLs being blocked by CORS? (Browser blocks cross-origin fetches from localhost to external APIs)
3. Is the state being set but the component not re-rendering?

**The most likely cause is CORS.** Browser-side fetch to `query1.finance.yahoo.com` is blocked in many environments. The fix is to proxy these calls through the backend.

### Fix A — Backend: Add `/market/indices` endpoint to `server.py`

Add this endpoint. It fetches NIFTY, SENSEX, USD/INR server-side (no CORS issue) and caches in Redis for 5 minutes.

```python
@app.get("/market/indices")
async def get_market_indices():
    cache_key = "market:indices"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return JSONResponse(json.loads(cached))
    except Exception:
        pass

    result = {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        # NIFTY 50
        try:
            async with session.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d",
                headers={"User-Agent": "Mozilla/5.0"}
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    meta = data["chart"]["result"][0]["meta"]
                    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or meta["regularMarketPrice"]
                    change_pct = ((meta["regularMarketPrice"] - prev) / prev * 100) if prev else 0
                    result["nifty"] = {
                        "price": round(meta["regularMarketPrice"], 2),
                        "change_pct": round(change_pct, 2)
                    }
        except Exception as e:
            result["nifty"] = {"error": str(e)}

        # SENSEX
        try:
            async with session.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d",
                headers={"User-Agent": "Mozilla/5.0"}
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    meta = data["chart"]["result"][0]["meta"]
                    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or meta["regularMarketPrice"]
                    change_pct = ((meta["regularMarketPrice"] - prev) / prev * 100) if prev else 0
                    result["sensex"] = {
                        "price": round(meta["regularMarketPrice"], 2),
                        "change_pct": round(change_pct, 2)
                    }
        except Exception as e:
            result["sensex"] = {"error": str(e)}

        # USD/INR
        try:
            async with session.get("https://open.er-api.com/v6/latest/USD") as r:
                if r.status == 200:
                    data = await r.json()
                    result["usd_inr"] = round(data["rates"]["INR"], 2)
        except Exception as e:
            result["usd_inr"] = None

    result["timestamp"] = datetime.utcnow().isoformat()

    try:
        await redis_client.set(cache_key, json.dumps(result), ex=300)
    except Exception:
        pass

    return JSONResponse(result)
```

Also add `import aiohttp` and `import json` at the top of `server.py` if not already present.

### Fix B — Backend: Add `/market/crypto` endpoint to `server.py`

```python
CRYPTO_SYMBOLS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"}

@app.get("/market/crypto/{symbol}")
async def get_crypto_quote(symbol: str):
    symbol = symbol.upper()
    if symbol not in CRYPTO_SYMBOLS:
        return JSONResponse({"error": "Unsupported crypto symbol"}, status_code=400)

    cache_key = f"crypto:{symbol}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return JSONResponse(json.loads(cached))
    except Exception:
        pass

    pair = f"{symbol}USDT"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        try:
            async with session.get(
                f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    price_usd = float(data["lastPrice"])
                    
                    # Get INR rate
                    inr_rate = 84.0  # fallback
                    try:
                        fx_cached = await redis_client.get("market:indices")
                        if fx_cached:
                            fx_data = json.loads(fx_cached)
                            inr_rate = fx_data.get("usd_inr", 84.0)
                    except Exception:
                        pass

                    result = {
                        "symbol": symbol,
                        "price_usd": price_usd,
                        "inr_price": round(price_usd * inr_rate, 2),
                        "change_pct": round(float(data["priceChangePercent"]), 2),
                        "volume": float(data["volume"]),
                        "high_24h": float(data["highPrice"]),
                        "low_24h": float(data["lowPrice"]),
                        "source": "Binance",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    try:
                        await redis_client.set(cache_key, json.dumps(result), ex=30)
                    except Exception:
                        pass
                    return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=503)
```

### Fix C — Frontend: `api.ts` — add the two new API calls

```typescript
export const mcpApi = {
  // ... existing methods

  getMarketIndices: async () => {
    const res = await api.get("/market/indices");
    return res.data;
  },

  getCryptoQuote: async (symbol: string) => {
    const res = await api.get(`/market/crypto/${symbol}`);
    return res.data;
  },
};
```

### Fix D — Frontend: `DashboardPage.tsx` — wire up real-time fetching

**Indian Market Overview section — replace existing fetch logic entirely:**

```typescript
// State
const [indices, setIndices] = useState<{
  nifty: { price: number; change_pct: number } | null;
  sensex: { price: number; change_pct: number } | null;
  usd_inr: number | null;
  loading: boolean;
}>({ nifty: null, sensex: null, usd_inr: null, loading: true });

// Fetch function
const fetchIndices = useCallback(async () => {
  try {
    const data = await mcpApi.getMarketIndices();
    setIndices({
      nifty: data.nifty?.price ? data.nifty : null,
      sensex: data.sensex?.price ? data.sensex : null,
      usd_inr: data.usd_inr ?? null,
      loading: false
    });
  } catch {
    setIndices(prev => ({ ...prev, loading: false }));
  }
}, []);

// Effect — fetch on mount, refresh every 5 minutes
useEffect(() => {
  fetchIndices();
  const id = setInterval(fetchIndices, 5 * 60 * 1000);
  return () => clearInterval(id);
}, [fetchIndices]);
```

**Indian Market Overview JSX:**

```tsx
<div className="indices-grid">
  {[
    {
      label: "NIFTY 50",
      value: indices.nifty?.price,
      change: indices.nifty?.change_pct,
      format: (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 2 })
    },
    {
      label: "SENSEX",
      value: indices.sensex?.price,
      change: indices.sensex?.change_pct,
      format: (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 2 })
    },
    {
      label: "USD / INR",
      value: indices.usd_inr,
      change: null,
      format: (v: number) => v.toFixed(2),
      subtitle: "Live reference FX rate"
    }
  ].map(({ label, value, change, format, subtitle }) => (
    <div key={label} className="index-card">
      <span className="index-label">{label}</span>
      {indices.loading || value == null ? (
        <div className="skeleton-line" style={{ height: 36, width: "70%", margin: "10px 0" }} />
      ) : (
        <>
          <div className="index-value">{format(value)}</div>
          {change != null && (
            <div className={`index-change ${change >= 0 ? "positive" : "negative"}`}>
              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
            </div>
          )}
          {subtitle && <div className="index-subtitle">{subtitle}</div>}
        </>
      )}
    </div>
  ))}
</div>
```

**For crypto search — when user searches BTC/ETH/known crypto symbol:**

```typescript
const CRYPTO_LIST = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"];

const handleSearch = async (sym: string) => {
  const upper = sym.toUpperCase();
  setLoading(true);
  try {
    if (CRYPTO_LIST.includes(upper)) {
      const data = await mcpApi.getCryptoQuote(upper);
      setQuote({
        symbol: data.symbol,
        price: data.inr_price,          // show INR
        price_usd: data.price_usd,
        change_pct: data.change_pct,
        high: data.high_24h,
        low: data.low_24h,
        volume: data.volume,
        source: data.source,
        asset_type: "crypto"
      });
    } else {
      const data = await mcpApi.invoke("quote.latest", { symbol: upper });
      setQuote(data);
    }
  } finally {
    setLoading(false);
  }
};
```

**QuoteCard — fix latency display:**
Find wherever `latency` is rendered and change to:
```tsx
{latency != null && (
  <span className="latency">{Number(latency).toFixed(2)} ms</span>
)}
```

---

## Problem 2: News Analysis Returning Memory Answer

### Root Cause Diagnosis
Run this in terminal before writing any code:
```bash
# Check if NEWS_API_KEY is set
grep -r "NEWS_API_KEY\|news_api_key" .env mcp_server/config.py

# Check if the news client actually calls the API
python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')
from finance_mcp.news_client import NewsClient
async def test():
    client = NewsClient()
    articles = await client.fetch_articles('NVIDIA chip export controls')
    print(f'Articles found: {len(articles)}')
    if articles:
        print(articles[0].title)
asyncio.run(test())
"
```

This will reveal one of three root causes:

**Cause A:** `NEWS_API_KEY` is not in `.env` → articles list is always empty → agent falls back to memory  
**Cause B:** NewsAPI free tier only returns articles up to 1 month old and blocks certain queries  
**Cause C:** `handle_news_analysis` has an exception being swallowed silently  

### Fix A — Verify and expose the API key

In `.env`:
```
NEWS_API_KEY=your_key_here
```

In `finance_mcp/news_client.py` — add startup validation:
```python
def __init__(self):
    self.api_key = settings.news_api_key
    if not self.api_key:
        raise RuntimeError(
            "NEWS_API_KEY is not configured. "
            "Set NEWS_API_KEY in your .env file. "
            "Get a free key at https://newsapi.org"
        )
    self.base_url = "https://newsapi.org/v2/everything"
```

### Fix B — Improve the news query construction

In `finance_mcp/news_client.py`, find `fetch_articles` and improve the query and date range:

```python
async def fetch_articles(self, query: str, days_back: int = 7) -> list[NewsArticle]:
    from datetime import datetime, timedelta
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 10,
        "apiKey": self.api_key
    }
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(self.base_url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    articles = data.get("articles", [])
                    if not articles and days_back < 30:
                        # Retry with broader date range
                        return await self.fetch_articles(query, days_back=30)
                    return [self._parse_article(a) for a in articles if a.get("title")]
                elif resp.status == 401:
                    raise RuntimeError("NewsAPI key is invalid or expired")
                elif resp.status == 429:
                    raise RuntimeError("NewsAPI rate limit hit")
                else:
                    body = await resp.text()
                    raise RuntimeError(f"NewsAPI error {resp.status}: {body[:200]}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"NewsAPI request failed: {e}")
```

### Fix C — Surface errors in `news_analysis.py` handler

In `mcp_server/invoke_handlers/news_analysis.py`, wrap the pipeline call so errors are explicit:

```python
async def handle_news_analysis(request: dict) -> dict:
    tool_input = request.get("tool_input", {})
    query = tool_input.get("query", "")
    ticker_anchor = tool_input.get("ticker_anchor")

    if not query:
        return {"error": "query parameter is required"}

    try:
        result = await run_news_ingestion_pipeline(query=query, ticker_anchor=ticker_anchor)
    except RuntimeError as e:
        # Surface the real error so the agent knows what happened
        return {
            "error": str(e),
            "query": query,
            "articles_found": 0,
            "direct_entities": [],
            "cascade": [],
            "agent_note": (
                f"News fetch failed: {e}. "
                "Tell the user you attempted to fetch live news but encountered an error. "
                "Provide relevant context from your training data with a clear disclaimer "
                "that it may not reflect the latest developments."
            )
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {e}",
            "articles_found": 0,
            "agent_note": "Tool failed unexpectedly. Acknowledge this to the user."
        }

    return result
```

### Fix D — Harden the chat agent system prompt (final version)

In `mcp_server/chat_agent.py`, replace the TOOL USAGE RULES section with:

```python
"""
TOOL USAGE RULES — THESE ARE MANDATORY AND NON-NEGOTIABLE:

1. NEWS & CURRENT EVENTS — HARD RULE:
   Any question about: news, recent events, what is happening, export controls, 
   sanctions, earnings results, regulatory changes, geopolitical events, market 
   disruptions, supply chain events, price movements, analyst upgrades/downgrades,
   or anything that could have changed in the past 7 days → YOU MUST call 
   `analyze_news_impact` FIRST. No exceptions.
   
   - Do NOT answer from training data before attempting the tool.
   - If the tool returns an error or empty results, THEN say:
     "I attempted to fetch the latest news but [reason]. Based on my training data 
     (which may not reflect the most recent developments): [answer]"
   - Never present training data as current fact.

2. STOCK PRICE / QUOTE → call `get_stock_quote`
   Any question about current price, market cap, P/E, volume, 52-week range.

3. SUPPLY CHAIN EXPOSURE → call `trace_supply_chain_impact`
   Which companies are affected by a disruption, supplier failure, commodity shock.

4. INVESTMENT ANALYSIS → call `multi_agent_analysis`
   Explicit requests for a thesis, recommendation, buy/sell/hold, full analysis.

5. ROUTING TIE-BREAKER:
   - Event/news-driven question → `analyze_news_impact`
   - Investment decision request → `multi_agent_analysis`
   - Both overlap → call `analyze_news_impact` first, then `multi_agent_analysis`

SCOPE ENFORCEMENT:
If the question is not about finance, markets, economics, or investment:
Reply exactly: "I'm QuantVex, a specialized financial intelligence assistant. 
I can only help with financial markets, investment analysis, and economic topics. 
What financial question can I help you with?"
"""
```

### Fix E — Add fallback: use web search if NewsAPI fails

If `NEWS_API_KEY` is unavailable or NewsAPI consistently fails, add a fallback in `news_client.py` using the GNews public API (no key required for basic use):

```python
async def fetch_articles_fallback(self, query: str) -> list[NewsArticle]:
    """Fallback: GNews API — no key required, 10 req/day free."""
    url = "https://gnews.io/api/v4/search"
    # GNews requires a key too — use this free alternative instead:
    # RSS-based approach via Google News RSS (no key, no CORS issue server-side)
    rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(rss_url) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    return self._parse_rss(content)
    except Exception:
        pass
    return []

def _parse_rss(self, xml_content: str) -> list[NewsArticle]:
    import xml.etree.ElementTree as ET
    articles = []
    try:
        root = ET.fromstring(xml_content)
        items = root.findall(".//item")[:10]
        for item in items:
            title = item.findtext("title", "").strip()
            url = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            if title and url:
                articles.append(NewsArticle(
                    title=title,
                    url=url,
                    published_at=pub_date,
                    source="Google News RSS",
                    content=title  # RSS only gives title; enough for parsing
                ))
    except Exception:
        pass
    return articles
```

In `fetch_articles`, call the fallback if primary returns empty:
```python
if not articles:
    articles = await self.fetch_articles_fallback(query)
```

---

## Verification Checklist

Run all 4 checks. Do not declare done until all pass.

**Check 1 — NIFTY/SENSEX live:**
```bash
curl http://localhost:8000/market/indices | python3 -m json.tool
# Must return: nifty.price in 22000-25000 range, sensex.price in 72000-82000 range
# usd_inr in 83-90 range. If any field is null or has "error", the fetch failed.
```

**Check 2 — Crypto live:**
```bash
curl http://localhost:8000/market/crypto/BTC | python3 -m json.tool
# Must return: price_usd > 50000 (BTC is not $33)
# inr_price = price_usd * usd_inr rate
```

**Check 3 — NewsAPI working:**
```bash
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from finance_mcp.news_client import NewsClient
async def t():
    c = NewsClient()
    arts = await c.fetch_articles('NVIDIA chip export controls')
    print(f'Articles: {len(arts)}')
    for a in arts[:3]: print(' -', a.title[:80])
asyncio.run(t())
"
# Must return at least 1 article. If 0, the fallback RSS must also be tested.
```

**Check 4 — Chat agent uses tool for news:**
POST to `/chat`:
```json
{"message": "what is happening with NVIDIA and AI chip export controls?"}
```
Response must either:
- Contain actual recent news article references, OR
- Explicitly say "I attempted to fetch live news but [reason]" — NOT silently answer from memory as if it were current.

**Check 5 — Dashboard UI:**
Open browser → Dashboard:
- NIFTY 50 card shows real number (not 0, not --, not placeholder)
- BTC search shows price > $50,000
- Latency shows as `X.XX ms` not 15+ decimal places
# QuantVex — Final Polish Fix Document

**Scope:** 5 targeted fixes. Do not touch anything else.  
**Goal:** Ship-ready frontend and chat agent improvements only.  
**Token budget:** Minimal — read only the files you need to change.

---

## Fix 1 — Dashboard: Indian Market Overview shows stale/placeholder values

**File:** `frontend/src/DashboardPage.tsx`

**Problem:** NIFTY 50, SENSEX, and USD/INR cards are showing hardcoded or cached placeholder values instead of live fetched data.

**Fix:** The Indian Market Overview section must fetch live data on mount and refresh every 5 minutes. Use these free public endpoints — no API key required:

```typescript
// USD/INR — use the backend cached rate already available
const fxRate = await mcpApi.invoke("quote.latest", { symbol: "USD_INR" });
// Fallback: fetch from https://open.er-api.com/v6/latest/USD (free, no key)

// NIFTY 50 — use Yahoo Finance unofficial quote endpoint
// GET https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d
// Parse: result[0].meta.regularMarketPrice and result[0].meta.regularMarketChangePercent

// SENSEX — same pattern
// GET https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d
```

Implementation pattern:

```typescript
const fetchIndianMarket = async () => {
  try {
    const [niftyRes, sensexRes, fxRes] = await Promise.allSettled([
      fetch("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d"),
      fetch("https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d"),
      fetch("https://open.er-api.com/v6/latest/USD")
    ]);

    if (niftyRes.status === "fulfilled") {
      const data = await niftyRes.value.json();
      const meta = data.chart.result[0].meta;
      setNifty({ price: meta.regularMarketPrice, change: meta.regularMarketChangePercent });
    }
    if (sensexRes.status === "fulfilled") {
      const data = await sensexRes.value.json();
      const meta = data.chart.result[0].meta;
      setSensex({ price: meta.regularMarketPrice, change: meta.regularMarketChangePercent });
    }
    if (fxRes.status === "fulfilled") {
      const data = await fxRes.value.json();
      setUsdInr(data.rates.INR);
    }
  } catch (e) {
    // Silently fail — keep previous values, do not crash
  }
};

useEffect(() => {
  fetchIndianMarket();
  const interval = setInterval(fetchIndianMarket, 5 * 60 * 1000);
  return () => clearInterval(interval);
}, []);
```

While loading, show a skeleton shimmer on each card (same dimensions, animated background). Never show "--" or "0" as a price value — show the skeleton until data arrives.

Format the change percent with a `+` prefix for positive values, color green (`#24a148`) for positive, red (`#da1e28`) for negative.

---

## Fix 2 — Dashboard: Crypto prices incorrect (BTC shows $33.77)

**File:** `frontend/src/DashboardPage.tsx` and/or `mcp_server/invoke_handlers/quote_latest.py`

**Problem:** BTC is returning $33.77 — this is wildly wrong. Bitcoin price is ~$90,000+. The issue is the quote handler is treating BTC as a stock ticker and hitting Finnhub/Alpha Vantage which either return nothing or a garbage value, which then gets divided incorrectly.

**Fix — Backend (`quote_latest.py`):**

Detect crypto symbols before hitting stock connectors. Add a crypto symbol list check:

```python
CRYPTO_SYMBOLS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC"}

async def handle_quote_latest(request: dict) -> dict:
    symbol = request["tool_input"]["symbol"].upper()
    
    if symbol in CRYPTO_SYMBOLS:
        return await fetch_crypto_quote(symbol)
    # ... existing stock logic
```

```python
async def fetch_crypto_quote(symbol: str) -> dict:
    """Fetch crypto price from Binance public API — no key required."""
    pair = f"{symbol}USDT"
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                price_usd = float(data["lastPrice"])
                change_pct = float(data["priceChangePercent"])
                # Get INR rate from cache
                inr_rate = await get_cached_inr_rate()
                return {
                    "symbol": symbol,
                    "price": price_usd,
                    "inr_price": round(price_usd * inr_rate, 2),
                    "change_percent": change_pct,
                    "volume": float(data["volume"]),
                    "asset_type": "crypto",
                    "source": "Binance",
                    "currency": "USD"
                }
    return {"symbol": symbol, "error": "Crypto price unavailable"}
```

Also fix the `Latency` field displaying as `69.19169425964355 ms` — round it to 2 decimal places everywhere it is displayed in the frontend: `${latency.toFixed(2)} ms`.

---

## Fix 3 — Dashboard: Remove "AI Market Insights" and "Recent Market Events" sections

**File:** `frontend/src/DashboardPage.tsx`

**Problem:** The AI Market Insights cards show internal debug text ("DataSource.FINNHUB, cache=False") and the Recent Market Events are hardcoded/fake. Both sections look unprofessional and cluttered.

**Fix:** Remove both sections entirely from the Dashboard JSX. Replace with a single clean "Market Intelligence" banner that links to the Chat page:

```tsx
{/* Replace AI Market Insights + Recent Market Events with this */}
<div className="market-intelligence-cta">
  <div className="cta-content">
    <h3>AI Market Intelligence</h3>
    <p>
      Ask about supply chain risks, company analysis, live news impact, 
      and multi-agent investment theses.
    </p>
  </div>
  <button 
    className="btn-primary"
    onClick={() => navigate("/chat")}
  >
    Open AI Analyst →
  </button>
</div>
```

CSS for this banner:
```css
.market-intelligence-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px 32px;
  background: linear-gradient(135deg, #111118 0%, #16161f 100%);
  border: 1px solid #282836;
  border-left: 4px solid #0f62fe;
  border-radius: 12px;
  margin-top: 32px;
}
.market-intelligence-cta h3 {
  font-size: 18px;
  font-weight: 600;
  color: #f4f4f4;
  margin: 0 0 6px 0;
}
.market-intelligence-cta p {
  font-size: 14px;
  color: #a8a8b3;
  margin: 0;
  max-width: 520px;
}
```

The Dashboard layout after this change should be: Indian Market Overview → Market Data (search + chart + quote card) → Market Intelligence CTA. Clean, three sections, nothing fake.

---

## Fix 4 — Chat: Response formatting must look professional

**Files:** `frontend/src/StructuredAnalysisMessage.tsx`, `frontend/src/index.css`

**Problem:** The multi-agent analysis response renders as plain bullet points with no visual hierarchy, no color coding on verdict/confidence, and no separation between sections. It looks like raw text.

**Target quality:** Match Claude-style response formatting — clean typography, clear visual hierarchy, color-coded verdict, side-by-side bull/bear layout, confidence shown as a visual bar.

**Fix — `StructuredAnalysisMessage.tsx`:**

Replace the current card rendering with this structure:

```tsx
// Verdict header strip — full width, color coded
<div className="verdict-strip" style={{ borderColor: verdictColor }}>
  <div className="verdict-left">
    <span className="verdict-badge" style={{ background: verdictColor }}>
      {verdict}
    </span>
    <span className="conviction-label">Conviction: {conviction}</span>
    <span className="horizon-label">⏱ {timeHorizon}</span>
  </div>
  <div className="confidence-meter">
    <span className="confidence-label">Composite Confidence</span>
    <div className="confidence-bar-track">
      <div 
        className="confidence-bar-fill"
        style={{ width: `${compositeConfidence}%`, background: verdictColor }}
      />
    </div>
    <span className="confidence-value">{compositeConfidence}%</span>
  </div>
</div>

// Summary — clean paragraph, no bullets
<div className="analysis-summary">
  <p>{summary}</p>
</div>

// Bull / Bear — two columns side by side
<div className="thesis-grid">
  <div className="thesis-card bull">
    <div className="thesis-header">
      <span className="thesis-icon">▲</span>
      <h4>Bull Case</h4>
      <span className="thesis-confidence">{bullConfidence}%</span>
    </div>
    <div className="confidence-mini-bar">
      <div style={{ width: `${bullConfidence}%`, background: "#24a148" }} />
    </div>
    <p className="thesis-reasoning">{bullReasoning}</p>
    <ul className="driver-list bull-drivers">
      {bullDrivers.map((d, i) => <li key={i}><span>▲</span>{d}</li>)}
    </ul>
  </div>

  <div className="thesis-card bear">
    <div className="thesis-header">
      <span className="thesis-icon">▼</span>
      <h4>Bear Case</h4>
      <span className="thesis-confidence">{bearConfidence}%</span>
    </div>
    <div className="confidence-mini-bar">
      <div style={{ width: `${bearConfidence}%`, background: "#da1e28" }} />
    </div>
    <p className="thesis-reasoning">{bearReasoning}</p>
    <ul className="driver-list bear-drivers">
      {bearDrivers.map((d, i) => <li key={i}><span>▼</span>{d}</li>)}
    </ul>
  </div>
</div>

// Conclusion — bottom strip
<div className="analysis-conclusion">
  <h4>Conclusion</h4>
  <p>{conclusion}</p>
</div>
```

**CSS to add to `index.css`:**

```css
/* Verdict strip */
.verdict-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  background: #16161f;
  border: 1px solid #282836;
  border-left: 4px solid;
  border-radius: 12px 12px 0 0;
  flex-wrap: wrap;
  gap: 12px;
}
.verdict-badge {
  display: inline-block;
  padding: 4px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.5px;
}
.conviction-label, .horizon-label {
  font-size: 13px;
  color: #a8a8b3;
  margin-left: 12px;
}
.verdict-left { display: flex; align-items: center; }
.confidence-meter { display: flex; align-items: center; gap: 8px; }
.confidence-bar-track {
  width: 120px; height: 6px;
  background: #282836; border-radius: 3px; overflow: hidden;
}
.confidence-bar-fill { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
.confidence-value { font-size: 13px; font-weight: 600; color: #f4f4f4; }

/* Summary */
.analysis-summary {
  padding: 20px 24px;
  background: #111118;
  border-left: 1px solid #282836;
  border-right: 1px solid #282836;
}
.analysis-summary p { font-size: 15px; color: #c8c8d0; line-height: 1.7; margin: 0; }

/* Thesis grid */
.thesis-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: #282836;
}
@media (max-width: 768px) { .thesis-grid { grid-template-columns: 1fr; } }

.thesis-card {
  padding: 20px 24px;
  background: #111118;
}
.thesis-card.bull { border-top: 2px solid #24a148; }
.thesis-card.bear { border-top: 2px solid #da1e28; }

.thesis-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
}
.thesis-header h4 { font-size: 14px; font-weight: 600; color: #f4f4f4; margin: 0; flex: 1; }
.thesis-icon { font-size: 12px; }
.thesis-card.bull .thesis-icon { color: #24a148; }
.thesis-card.bear .thesis-icon { color: #da1e28; }
.thesis-confidence { font-size: 13px; font-weight: 700; }
.thesis-card.bull .thesis-confidence { color: #24a148; }
.thesis-card.bear .thesis-confidence { color: #da1e28; }

.confidence-mini-bar {
  height: 3px; background: #282836;
  border-radius: 2px; overflow: hidden; margin-bottom: 14px;
}
.confidence-mini-bar div { height: 100%; border-radius: 2px; }

.thesis-reasoning { font-size: 13px; color: #a8a8b3; line-height: 1.6; margin: 0 0 14px 0; }

.driver-list { list-style: none; padding: 0; margin: 0; }
.driver-list li {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 13px; color: #c8c8d0; padding: 5px 0;
  border-bottom: 1px solid #1e1e2a;
}
.driver-list li:last-child { border-bottom: none; }
.bull-drivers li span { color: #24a148; font-size: 10px; padding-top: 3px; flex-shrink: 0; }
.bear-drivers li span { color: #da1e28; font-size: 10px; padding-top: 3px; flex-shrink: 0; }

/* Conclusion */
.analysis-conclusion {
  padding: 18px 24px;
  background: #16161f;
  border: 1px solid #282836;
  border-top: none;
  border-radius: 0 0 12px 12px;
}
.analysis-conclusion h4 { font-size: 13px; font-weight: 600; color: #a8a8b3; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; }
.analysis-conclusion p { font-size: 14px; color: #c8c8d0; line-height: 1.6; margin: 0; }
```

**Verdict color map** (must be defined in the component):
```typescript
const VERDICT_COLORS: Record<string, string> = {
  "STRONG BUY": "#24a148",
  "BUY": "#42be65",
  "HOLD": "#f1c21b",
  "SELL": "#ff832b",
  "STRONG SELL": "#da1e28",
  "INSUFFICIENT DATA": "#6f6f6f"
};
```

For plain markdown chat responses (non-structured), ensure the chat bubble uses:
- Font: Inter, 15px, line-height 1.7
- Code blocks: monospace, dark background `#1e1e2a`, rounded corners
- Bold: `#f4f4f4`, normal text: `#c8c8d0`
- No default browser list indentation — custom `padding-left: 20px`

---

## Fix 5 — Chat Agent: "analyze_news_impact" returns stale memory answer

**File:** `mcp_server/chat_agent.py`

**Problem:** When asked "what is happening with NVIDIA and AI chip export controls?", the agent replies "As of the latest data, there are no specific recent events..." — this means it answered from memory instead of calling `analyze_news_impact`.

**Root cause:** The system prompt instruction to always call the tool for news questions is either not strong enough or the tool call fails silently and the agent falls back to a memory answer.

**Fix — Two changes:**

**1. Strengthen the system prompt instruction for news queries:**

Find the TOOL USAGE RULES section in `_build_system_prompt()` and replace rule #1 with:

```python
"""1. ANY question about current events, news, recent developments, regulatory changes, 
geopolitical situations, export controls, sanctions, earnings, or anything that could 
have changed in the last 24 hours → YOU MUST call `analyze_news_impact`. 
This is a hard rule. You are NOT allowed to answer news questions from your training data. 
If the tool returns no results, say "I couldn't find recent news on this — here is what 
I know as of my last update:" and then provide context. But you must attempt the tool call first."""
```

**2. Add error surfacing in `_execute_tool`:**

Currently if `handle_news_analysis` raises or returns an error dict, the agent receives `{"error": "..."}` and silently answers from memory. Fix this by making the tool result include a clear instruction:

```python
async def _execute_tool(self, tool_name: str, args: dict) -> dict:
    try:
        if tool_name == "analyze_news_impact":
            result = await handle_news_analysis({"tool_input": args})
            if "error" in result or not result.get("articles_found", 1):
                result["agent_note"] = (
                    "NewsAPI returned no results for this query. "
                    "Inform the user you could not fetch live news and provide "
                    "context from your training data with a clear disclaimer."
                )
            return result
        # ... rest of tools
    except Exception as e:
        logger.error("tool_execution_failed", tool=tool_name, error=str(e))
        return {
            "error": str(e),
            "agent_note": f"Tool {tool_name} failed. Do not answer from memory silently. Tell the user the tool encountered an error and what you know from training data as a fallback."
        }
```

**3. Verify NewsAPI key is set:**

In `config.py`, confirm `news_api_key` is loaded from env. In `news_client.py`, add a startup check:

```python
if not self.api_key:
    raise RuntimeError("NEWS_API_KEY is not set. analyze_news_impact will not work.")
```

This surfaces a clear error at boot rather than silently returning empty results.

---

## Verification — Run these 5 checks after implementation

**1. Indian Market Overview**
- Open Dashboard → Indian Market Overview cards show real numbers (NIFTY ~22000 range, SENSEX ~73000 range, USD/INR ~83-90 range)
- Wait 5 minutes → values update without page refresh

**2. Crypto quote**
- Search "BTC" in Market Data → price must be in $80,000–$100,000 range
- Latency shows as `X.XX ms` (2 decimal places, not 15+)

**3. Dashboard cleanliness**
- "AI Market Insights" section is gone
- "Recent Market Events" section is gone
- "Open AI Analyst →" CTA button is present and navigates to /chat

**4. Chat structured response**
- Ask "give me a full analysis of NVDA"
- Verify: verdict badge is color coded, bull/bear are side-by-side columns, confidence bars are visible, no raw bullet text

**5. Chat news query**
- Ask "what is happening with NVIDIA and AI chip export controls?"
- Verify: response references actual recent news OR explicitly states it attempted to fetch news and fell back to training data with a disclaimer — NOT a silent memory answer presented as current fact
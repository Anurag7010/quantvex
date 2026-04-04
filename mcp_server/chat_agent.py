"""
Gemini Chat Agent for MCP Server
"""
import asyncio
from typing import Dict, Any, Optional
import google.generativeai as genai

from mcp_server.config import get_settings
from mcp_server.invoke_handlers import handle_quote_latest, handle_trace_impact
from mcp_server.invoke_handlers.news_analysis import handle_news_analysis
from mcp_server.invoke_handlers.multi_agent_analysis import handle_multi_agent_analysis
from mcp_server.utils.logging import get_logger

from finance_formatter import format_financial_report

logger = get_logger(__name__)

# Exchange rate for INR conversion
USD_TO_INR = 89.94


def _normalize_quote(symbol: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize MCP quote payload into INR fields for formatter."""
    base_symbol = (symbol or "").upper() or "N/A"
    
    if not result.get("success"):
        return {"symbol": base_symbol, "error": result.get("error", "Unknown error")}
    
    data = result.get("data", {})
    
    def to_inr(value: Optional[float]) -> Optional[float]:
        return round(value * USD_TO_INR, 2) if value is not None else None
    
    price = to_inr(data.get("price"))
    prev = to_inr(data.get("previous_close"))
    open_px = to_inr(data.get("open"))
    high = to_inr(data.get("high"))
    low = to_inr(data.get("low"))
    
    change = None
    change_pct = None
    if price is not None and prev not in (None, 0):
        change = round(price - prev, 2)
        change_pct = round((change / prev) * 100, 2)
    
    return {
        "symbol": data.get("symbol", base_symbol).upper(),
        "price": price,
        "previous_close": prev,
        "open": open_px,
        "high": high,
        "low": low,
        "volume": data.get("volume"),
        "change": change,
        "change_pct": change_pct,
        "data_source": data.get("data_source", "Real-time market data via MCP financial server"),
        "cache_state": "cached" if data.get("cache_hit") else "fresh",
    }


def _dedupe_points(items: list[str], min_points: int = 3) -> list[str]:
    unique: list[str] = []
    seen = set()
    for item in items:
        cleaned = " ".join(str(item).split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)

    while len(unique) < min_points:
        unique.append("Signal coverage is currently limited; monitor incoming market updates.")

    return unique[:max(min_points, 5)]


def _outlook_from_verdict(verdict: str) -> str:
    text = (verdict or "").lower()
    if "bull" in text:
        return "Bullish"
    if "bear" in text:
        return "Bearish"
    return "Mixed"


class GeminiChatAgent:
    """Gemini-powered chat agent with MCP tool access"""
    
    def __init__(self):
        settings = get_settings()
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        
        genai.configure(api_key=settings.gemini_api_key)
        self.tools = self._create_tools()
        
    def _create_tools(self):
        """Define Gemini function calling tools"""
        return [
            genai.protos.Tool(
                function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name="get_stock_quote",
                        description="Get the latest stock or cryptocurrency price quote. Use this for any questions about current prices, stock values, market data, or financial instrument values.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "symbol": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Stock ticker symbol (e.g., AAPL, MSFT, GOOGL, TSLA) or crypto pair (e.g., BTCUSDT, ETHUSDT, SOLUSDT)"
                                ),
                                "max_age_sec": genai.protos.Schema(
                                    type=genai.protos.Type.INTEGER,
                                    description="Maximum age of cached data in seconds. Default is 60."
                                )
                            },
                            required=["symbol"]
                        )
                    ),
                    genai.protos.FunctionDeclaration(
                        name="trace_supply_chain_impact",
                        description=(
                            "Query the supply-chain knowledge graph to find companies that directly "
                            "depend on a specific company. Use this ONLY when: "
                            "(1) the user asks 'who depends on X' or 'what companies depend on X' "
                            "WITHOUT referencing any current news event, conflict, war, or crisis; AND "
                            "(2) you already know the exact ticker symbol. "
                            "DO NOT use this for geopolitical events, wars, sanctions, shortages, "
                            "factory fires, or anything mentioning a real-world current situation — "
                            "use analyze_news_impact instead for all those cases."
                        ),
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "ticker": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description=(
                                        "Ticker symbol of the company or commodity at the disruption source. "
                                        "Examples: TSMC (chips), XOM (oil), CVX (oil), ASML (lithography). "
                                        "Use uppercase, 1-64 characters, letters/digits/underscore/dot/hyphen only."
                                    )
                                ),
                                "max_hops": genai.protos.Schema(
                                    type=genai.protos.Type.INTEGER,
                                    description="How many supply-chain levels deep to traverse. Default 2, maximum 5. Use 3 for broader analysis."
                                ),
                            },
                            required=["ticker"]
                        )
                    ),
                    genai.protos.FunctionDeclaration(
                        name="analyze_news_impact",
                        description=(
                            "Fetch LIVE real-time news about a geopolitical event, conflict, commodity disruption, "
                            "or supply chain shock — then automatically identify which companies are directly "
                            "mentioned in the news AND which downstream companies depend on them via the supply "
                            "chain knowledge graph. Use this tool for ANY question that involves: "
                            "current events + stock impact, war or conflict + stock, sanctions + companies, "
                            "commodity shortage (oil, semiconductors, lithium, gas) + stocks, "
                            "'which stocks will be affected by [event]', 'what happens to [sector] if [event]'. "
                            "This tool fetches REAL news articles, parses them for disruption signals, writes "
                            "events to the graph, and returns a full cascade analysis. "
                            "ALWAYS prefer this over trace_supply_chain_impact when the user mentions a current "
                            "news event, geopolitical situation, OR asks which stocks are affected by something "
                            "happening in the real world."
                        ),
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "query": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description=(
                                        "NewsAPI search query to find relevant articles. Be specific: include "
                                        "country names, company names, commodity types, and event keywords. "
                                        "Examples: 'Iran USA war oil sanctions 2026', "
                                        "'China semiconductor export ban chips', "
                                        "'Taiwan TSMC factory disruption', "
                                        "'lithium shortage electric vehicles battery', "
                                        "'Russia gas supply Europe sanctions'."
                                    )
                                ),
                                "limit": genai.protos.Schema(
                                    type=genai.protos.Type.INTEGER,
                                    description="Number of news articles to analyze. Default 10, max 20."
                                ),
                                "max_hops": genai.protos.Schema(
                                    type=genai.protos.Type.INTEGER,
                                    description="Supply chain traversal depth. Default 2, max 5."
                                ),
                                "ticker": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description=(
                                        "Optional: the company or commodity ticker at the CENTRE of "
                                        "the disruption. When provided, the graph cascade ALWAYS runs "
                                        "— even if the news pipeline fails or the NER misses the entity. "
                                        "Include this whenever the user's question names a specific company. "
                                        "Examples: TSMC factory fire → ticker='TSMC'; "
                                        "Iran oil war → ticker='CRUDE_OIL'; "
                                        "US China chip ban → ticker='TSMC'; "
                                        "ASML export restrictions → ticker='ASML'."
                                    )
                                ),
                            },
                            required=["query"]
                        )
                    ),
                    genai.protos.FunctionDeclaration(
                        name="multi_agent_analysis",
                        description=(
                            "Run a structured multi-agent financial debate (bull vs bear) and "
                            "produce a balanced final verdict. Use this for impact-analysis "
                            "questions such as: 'what will happen to stocks if...', 'is this "
                            "bullish or bearish', geopolitical effects, and macro risk/reward "
                            "trade-off scenarios."
                        ),
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "query": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Natural-language market impact question."
                                ),
                                "ticker": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Optional anchor ticker for focused analysis."
                                ),
                            },
                            required=["query"]
                        )
                    ),
                ]
            )
        ]
    
    async def _execute_tool(self, function_name: str, function_args: Dict[str, Any]) -> str:
        """Execute a tool call and return formatted result"""
        
        if function_name == "get_stock_quote":
            symbol = function_args.get("symbol", "AAPL")
            max_age = function_args.get("max_age_sec", 60)
            
            try:
                # Call the MCP handler directly
                result = await handle_quote_latest(
                    symbol=symbol,
                    max_age_sec=max_age,
                    agent_id="gemini_chat_agent",
                    query_text=f"Get quote for {symbol}"
                )
                
                if hasattr(result, 'model_dump'):
                    result = result.model_dump()
                
                # Normalize quote to formatter structure
                normalized_quote = _normalize_quote(symbol, result)
                
                # Use formatter for professional output
                formatted_response = format_financial_report({"quotes": [normalized_quote]})
                return formatted_response
            
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                return f"Error executing tool: {str(e)}"
        
        elif function_name == "trace_supply_chain_impact":
            ticker = function_args.get("ticker", "")
            # Gemini returns INTEGER schema values as float (e.g. 2.0).
            # Cast explicitly so handle_trace_impact's isinstance(max_hops, int) check passes.
            max_hops = int(function_args.get("max_hops", 2))

            try:
                result = await handle_trace_impact(
                    ticker=ticker,
                    max_hops=max_hops,
                    agent_id="gemini_chat_agent",
                )

                if result.success and result.data:
                    companies = result.data.get("impacted_companies", [])
                    count = result.data.get("impacted_count", 0)
                    source_ticker = result.data.get("ticker", ticker.upper())
                    latency = result.latency_ms

                    if count == 0:
                        return (
                            f"No downstream supply-chain dependents found for {source_ticker} "
                            f"within {max_hops} hop(s). The company may not yet have dependency "
                            f"edges in the knowledge graph."
                        )

                    lines = [
                        f"Supply chain impact from {source_ticker} "
                        f"({count} downstream {'company' if count == 1 else 'companies'} found, "
                        f"{max_hops} hop{'s' if max_hops != 1 else ''}, {latency:.0f}ms):",
                        "",
                    ]
                    for c in companies:
                        lines.append(
                            f"• {c.get('ticker', '?')} — {c.get('name', 'Unknown')} "
                            f"[{c.get('sector', 'Unknown sector')}]"
                        )
                    return "\n".join(lines)
                else:
                    return f"Supply chain query failed: {result.error}"

            except Exception as e:
                logger.error(f"trace_supply_chain_impact error: {e}")
                return f"Error running supply chain analysis: {str(e)}"

        elif function_name == "analyze_news_impact":
            query = function_args.get("query", "")
            limit = int(function_args.get("limit", 10))
            max_hops = int(function_args.get("max_hops", 2))
            ticker = function_args.get("ticker") or None

            try:
                result = await handle_news_analysis(
                    query=query,
                    limit=limit,
                    max_hops=max_hops,
                    ticker=ticker,
                    agent_id="gemini_chat_agent",
                )

                if not result.success:
                    return f"News analysis failed: {result.error}"

                d = result.data
                articles = d.get("articles_fetched", 0)
                events = d.get("events_found", 0)
                ingested = d.get("events_ingested", 0)
                direct = d.get("directly_affected", [])
                cascade = d.get("downstream_cascade", {})
                total_cascade = d.get("total_cascade_companies", 0)
                news_events = d.get("news_events", [])
                latency = result.latency_ms or 0

                # news_available=False means pipeline failed or no articles —
                # but we may still have cascade data from the ticker anchor.
                news_available = d.get("news_available", articles > 0)
                pipeline_error = d.get("pipeline_error")
                msg_prefix = d.get("message", "")

                if not news_available and total_cascade == 0:
                    reason = pipeline_error or "no articles matched the query"
                    suggestion = (
                        f" You can ask me to 'trace supply chain of {ticker}' "
                        "to query the graph directly."
                    ) if ticker else " Try broader search terms or include a ticker."
                    return (
                        f"\u26a0\ufe0f No news articles found for \"{query}\" ({reason}).\n"
                        f"{suggestion}"
                    )

                # Build name lookup for cascade display
                ticker_name_map = {
                    e["ticker"]: e["name"]
                    for e in direct
                    if e["type"] == "company"
                }

                if news_available:
                    header = (
                        f"Live News Impact Analysis — \"{query}\" ({latency:.0f}ms)\n"
                        f"Fetched {articles} articles · {events} disruption events detected · "
                        f"{ingested} written to knowledge graph"
                    )
                else:
                    err_note = f" (news pipeline error: {pipeline_error})" if pipeline_error else " (no matching news)"
                    header = (
                        f"Supply Chain Analysis — \"{query}\" ({latency:.0f}ms)\n"
                        f"\u26a0\ufe0f News unavailable{err_note} — showing graph-only cascade for {ticker or 'provided entities'}"
                    )

                lines = [header, ""]

                if news_events:
                    lines.append("Disruption signals found in news:")
                    for ev in news_events[:5]:
                        lines.append(
                            f"• [{ev['event_type'].replace('_',' ').upper()} · "
                            f"severity {ev['severity']}/10] {ev['headline']}"
                        )
                    lines.append("")

                if not direct:
                    lines.append(
                        "No specific companies or commodities identified in these articles. "
                        "The event affects the market broadly or involves entities not yet "
                        "in the supply chain knowledge graph."
                    )
                    return "\n".join(lines)

                # Directly disrupted commodities
                direct_comms = [e for e in direct if e["type"] == "commodity"]
                direct_cos = [e for e in direct if e["type"] == "company"]

                if direct_comms:
                    lines.append("Commodities directly disrupted:")
                    for c in direct_comms:
                        lines.append(f"• {c['ticker']} — {c['name']}")
                    lines.append("")

                if direct_cos:
                    lines.append("Companies directly mentioned in news:")
                    for c in direct_cos:
                        lines.append(f"• {c['ticker']} — {c['name']}")
                    lines.append("")

                # Downstream cascade
                if cascade:
                    lines.append(
                        f"Downstream supply-chain cascade "
                        f"({total_cascade} unique companies at risk, {max_hops}-hop traversal):"
                    )
                    for source_ticker, dependents in cascade.items():
                        if dependents:
                            src_name = ticker_name_map.get(source_ticker, source_ticker)
                            lines.append(
                                f"\n  From {source_ticker} ({src_name}) disruption "
                                f"→ {len(dependents)} downstream:"
                            )
                            for dep in dependents:
                                lines.append(
                                    f"    • {dep.get('ticker','?')} — "
                                    f"{dep.get('name','Unknown')} "
                                    f"[{dep.get('sector','Unknown')}]"
                                )
                else:
                    lines.append(
                        "No downstream cascade found for the directly affected companies. "
                        "The knowledge graph may not yet contain dependency edges "
                        "for these entities."
                    )

                return "\n".join(lines)

            except Exception as e:
                logger.error(f"analyze_news_impact error: {e}")
                return f"Error running news impact analysis: {str(e)}"

        elif function_name == "multi_agent_analysis":
            query = function_args.get("query", "")
            ticker = function_args.get("ticker") or None

            try:
                result = await handle_multi_agent_analysis(
                    query=query,
                    ticker=ticker,
                    agent_id="gemini_chat_agent",
                )

                if not result.success or not result.data:
                    return f"Multi-agent analysis failed: {result.error}"

                d = result.data
                bull_case = d.get("bull_case", {})
                bear_case = d.get("bear_case", {})
                final_verdict = d.get("final_verdict", "No verdict")
                confidence = float(d.get("confidence", 0.0))
                summary = d.get("summary", "")
                key_drivers = d.get("key_drivers", [])

                resolved_ticker = d.get("ticker") or ticker or "MARKET"
                outlook = _outlook_from_verdict(final_verdict)

                bull_signals = _dedupe_points(list(bull_case.get("signals") or []), min_points=3)
                bear_signals = _dedupe_points(list(bear_case.get("signals") or []), min_points=3)
                insight_points = _dedupe_points([
                    *list(key_drivers or []),
                    f"Final verdict bias: {final_verdict}",
                    f"Net confidence spread: {abs(float(bull_case.get('confidence', 0.0)) - float(bear_case.get('confidence', 0.0))) * 100:.0f}%",
                ], min_points=3)

                bull_rationale = str(bull_case.get("reasoning", "Bull-side conviction is currently data-limited.")).strip()
                bear_rationale = str(bear_case.get("reasoning", "Bear-side conviction is currently data-limited.")).strip()

                # Optional market price enrichment for the Market Data section.
                current_price = "N/A"
                trend_insight = "Directional view is based on signal balance rather than direct price momentum."
                try:
                    if isinstance(resolved_ticker, str) and resolved_ticker and resolved_ticker.isalnum():
                        quote = await handle_quote_latest(
                            symbol=resolved_ticker,
                            max_age_sec=60,
                            agent_id="gemini_chat_agent",
                            query_text=f"Get quote for {resolved_ticker}",
                        )
                        if quote.success and quote.data and quote.data.get("price") is not None:
                            current_price = f"${float(quote.data['price']):.2f}"
                            trend_insight = (
                                "Price context supports measured risk budgeting while watching catalyst volatility."
                                if outlook != "Bearish"
                                else "Price context warrants defensive positioning until risk catalysts stabilize."
                            )
                except Exception as quote_exc:  # noqa: BLE001
                    logger.warning(f"multi_agent_analysis quote enrichment failed: {quote_exc}")

                summary_lines = [s.strip() for s in str(summary).split(".") if s.strip()][:3]
                if not summary_lines:
                    summary_lines = [
                        "Risk and upside signals are both present across current evidence.",
                        "Portfolio stance should align with confidence and catalyst timing.",
                    ]

                lines = [
                    f"## 📊 Multi-Agent Market Analysis — {resolved_ticker}",
                    "",
                    "### ⚖️ Final Verdict",
                    f"- **Outlook:** {outlook}",
                    f"- **Confidence:** {int(confidence * 100)}%",
                    "- **Summary:**",
                ]
                lines.extend([f"  {line}." if not line.endswith(".") else f"  {line}" for line in summary_lines])

                lines.extend([
                    "",
                    "---",
                    "",
                    "### 🟢 Bull Case",
                    "**Key Drivers:**",
                ])
                lines.extend([f"- {point}" for point in bull_signals[:3]])
                lines.extend([
                    "",
                    "**Rationale:**",
                    bull_rationale,
                    "",
                    "---",
                    "",
                    "### 🔴 Bear Case",
                    "**Key Risks:**",
                ])
                lines.extend([f"- {point}" for point in bear_signals[:3]])
                lines.extend([
                    "",
                    "**Rationale:**",
                    bear_rationale,
                    "",
                    "---",
                    "",
                    "### 📈 Market Data",
                    f"- **Current Price:** {current_price}",
                    f"- **Trend Insight:** {trend_insight}",
                    "",
                    "---",
                    "",
                    "### 🔍 Key Insights",
                ])
                lines.extend([f"- {point}" for point in insight_points[:3]])

                return "\n".join(lines)

            except Exception as e:
                logger.error(f"multi_agent_analysis error: {e}")
                return f"Error running multi-agent analysis: {str(e)}"

        return f"Unknown function: {function_name}"
    
    async def chat(self, message: str, history: Optional[list] = None) -> str:
        """
        Send message to Gemini and return response
        
        Args:
            message: User message
            history: Optional chat history
            
        Returns:
            AI response text
        """
        try:
            # Initialize model
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                tools=self.tools,
                system_instruction="""You are a financial intelligence assistant powered by a real-time supply-chain knowledge graph.

You have four tools. Choose the correct one every time:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL 1 — get_stock_quote
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USE FOR: current price, stock value, crypto price, market quote, how is X performing.
NEVER fabricate prices — always call this tool.
Prices must be shown in Indian Rupees (₹). Convert: price_usd × 89.94.

Symbol mappings:
  Apple→AAPL  Microsoft→MSFT  Google→GOOGL  Amazon→AMZN  Tesla→TSLA
  NVIDIA→NVDA  Qualcomm→QCOM  Intel→INTC  AMD→AMD  TSMC→TSMC
  ExxonMobil→XOM  Chevron→CVX  Shell→SHEL  BP→BP
  Bitcoin→BTCUSDT  Ethereum→ETHUSDT  Solana→SOLUSDT

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL 2 — analyze_news_impact  ← USE THIS FOR ALL EVENTS AND DISRUPTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USE FOR (MANDATORY for these patterns):
  ✓ Any war, conflict, sanctions, embargo, military action
  ✓ Any factory shutdown, explosion, natural disaster affecting a company
  ✓ Any commodity shortage: oil, semiconductors, lithium, gas, rare earth
  ✓ Any geopolitical crisis: Taiwan, Iran, Russia, China trade war
  ✓ "which stocks are affected by [X]"
  ✓ "what companies will be hurt if [event]"
  ✓ "impact of [event] on stocks"

This tool fetches LIVE news, identifies disrupted entities, writes to the graph,
then traverses the full supply-chain cascade.

CRITICAL — always set ticker when you know the company or commodity:
  "TSMC factory fire"         → query="Taiwan TSMC factory fire semiconductor", ticker="TSMC"
  "Iran USA war oil"          → query="Iran USA war oil supply disruption", ticker="CRUDE_OIL"
  "US China semiconductor ban"→ query="US China chip semiconductor export ban", ticker="TSMC"
  "ASML export restrictions"  → query="ASML export restriction lithography EUV", ticker="ASML"
  "lithium shortage"          → query="lithium shortage supply battery EV", ticker="ALB"
  "Russia Ukraine gas war"    → query="Russia Ukraine war natural gas supply", ticker="NATURAL_GAS"
  "Taiwan crisis chips"       → query="Taiwan strait crisis semiconductor production", ticker="TSMC"
  "oil supply disruption"     → query="oil supply disruption Middle East OPEC", ticker="CRUDE_OIL"

Setting ticker = the central company/commodity VID guarantees the graph cascade
runs even if no news articles match — making results robust.

Use max_hops=2 (default) for most queries; max_hops=3 for broader analysis.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL 3 — trace_supply_chain_impact
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USE FOR: ONLY when user asks "who depends on X" in a static/academic sense,
with no mention of a real event, war, or crisis.
Example: "Show me all companies that depend on TSMC in the graph."

DO NOT use this tool if the user's question mentions:
  ✗ any war, conflict, crisis, shutdown, shortage, disruption
  ✗ any current news event or geopolitical situation
In those cases, use analyze_news_impact instead.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL 4 — multi_agent_analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USE FOR: any balanced risk/reward reasoning question where the user asks for
an outlook, verdict, or bull-vs-bear framing.

MANDATORY for patterns like:
    ✓ "is this bullish or bearish"
    ✓ "what will happen to stocks if..."
    ✓ "impact of X on markets / sector / stocks"
    ✓ geopolitical effects with both upside and downside channels

This tool runs a structured Bull Agent + Bear Agent + Judge synthesis and
returns a final verdict with confidence.

When TOOL 4 is used, keep the response in strict markdown sections with:
    - one H2 title line
    - H3 section headers
    - bullet lists for drivers/risks/insights
    - no duplicate sentences
    - concise analyst-report style wording

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AFTER RECEIVING TOOL RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Explain the business rationale for each affected company:
  • Why is this company at risk? What does it depend on?
  • What sector is it in? What is the economic chain?
  • Quantify the exposure where possible.
Be analytical, professional, and concise.

You SHOULD use professional Markdown formatting. Use **bold** for company names, headers for sections, and bullet points for lists to make the output easy to read."""
            )
            
            # Start or continue chat
            chat = model.start_chat(history=history or [])
            
            # Send user message
            response = chat.send_message(message)
            
            # Handle function calls
            while response.candidates[0].content.parts:
                # Collect all function calls
                function_calls = []
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call.name:
                        function_calls.append(part.function_call)
                
                if not function_calls:
                    break
                
                # Execute all functions
                function_responses = []
                for function_call in function_calls:
                    func_name = function_call.name
                    func_args = dict(function_call.args) if function_call.args else {}
                    
                    logger.info(f"Gemini calling: {func_name} with {func_args}")
                    
                    result = await self._execute_tool(func_name, func_args)
                    
                    function_responses.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=func_name,
                                response={"result": result}
                            )
                        )
                    )
                
                # Send function results back
                response = chat.send_message(
                    genai.protos.Content(parts=function_responses)
                )
            
            # Extract final text
            final_text = ""
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text'):
                    final_text += part.text
            
            return final_text
        
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise


# Singleton instance
_agent_instance: Optional[GeminiChatAgent] = None


def get_chat_agent() -> GeminiChatAgent:
    """Get or create chat agent instance"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = GeminiChatAgent()
    return _agent_instance

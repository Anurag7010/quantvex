"""
OpenAI GPT-4o chat agent for QuantVex.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from openai import AsyncOpenAI

from mcp_server.config import get_settings
from mcp_server.invoke_handlers import handle_quote_latest, handle_trace_impact
from mcp_server.invoke_handlers.multi_agent_analysis import handle_multi_agent_analysis
from mcp_server.invoke_handlers.news_analysis import handle_news_analysis
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

DOMAIN_REFUSAL = (
    "I'm QuantVex, a specialized financial intelligence assistant. I can only help "
    "with financial markets, investment analysis, and economic topics. What "
    "financial question can I help you with?"
)

_FINANCE_TERMS = frozenset(
    {
        "stock", "stocks", "market", "markets", "finance", "financial",
        "investment", "invest", "portfolio", "company", "companies",
        "earnings", "revenue", "valuation", "price", "quote", "ticker",
        "bond", "bonds", "commodity", "commodities", "currency", "crypto",
        "inflation", "gdp", "rates", "fed", "central bank", "supply chain",
        "geopolitical", "oil", "semiconductor", "lithium", "risk",
        "buy", "sell", "hold", "bullish", "bearish",
        # Extended — common in real finance queries
        "news", "impact", "disruption", "supply", "analysis", "analyze",
        "affected", "exposed", "exposure", "sector", "industry", "macro",
        "tariff", "tariffs", "sanction", "sanctions", "guidance", "forecast",
        "outlook", "thesis", "recommendation", "downstream", "upstream",
        "dependencies", "dependency", "trade", "export", "import",
        "chips", "chip", "copper", "cobalt", "steel", "aluminum",
        "tsmc", "nvidia", "apple", "intel", "samsung", "amd", "qualcomm",
        "microsoft", "amazon", "tesla", "broadcom", "asml", "micron",
        "index", "indices", "nifty", "sensex", "nasdaq", "s&p", "dow",
        "ipo", "dividend", "interest rate", "yield", "spread",
        "what happened", "which companies", "how much", "why did",
    }
)

_OUT_OF_SCOPE_TERMS = frozenset(
    {
        "football",
        "world cup",
        "cricket",
        "basketball",
        "soccer",
        "recipe",
        "movie",
        "music",
        "coding",
        "programming",
        "relationship",
        "homework",
    }
)


class QuantVexChatAgent:
    """OpenAI GPT-4o chat agent with QuantVex MCP tool access."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o"
        self.conversation_history: list[dict[str, Any]] = []
        self._tools = self._build_tools()
        self._system_prompt = self._build_system_prompt()

    def _build_tools(self) -> list[dict[str, Any]]:
        """Build OpenAI-compatible function tool declarations."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_stock_quote",
                    "description": (
                        "Retrieve the latest real-time market quote for a stock ticker symbol. "
                        "Use this for any question about current price, market cap, volume, "
                        "P/E ratio, or basic financial metrics of a specific company."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Uppercase stock ticker symbol, e.g. AAPL, MSFT, TSLA",
                            }
                        },
                        "required": ["symbol"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "trace_supply_chain_impact",
                    "description": (
                        "Trace supply chain dependencies to find all companies downstream of a "
                        "given supplier or commodity. Call this PROACTIVELY whenever the user "
                        "mentions a specific company name or ticker — even if they don't ask "
                        "about supply chains — to surface hidden dependency exposure. "
                        "Use hops=2 for standard queries, hops=3 for broad cascade analysis."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_vid": {
                                "type": "string",
                                "description": (
                                    "Graph vertex ID of the source node (company ticker or commodity "
                                    "name). Example: 'AAPL' or 'CRUDE_OIL'"
                                ),
                            },
                            "hops": {
                                "type": "integer",
                                "description": (
                                    "Number of dependency hops to traverse. Default 3. Use higher "
                                    "values for broad cascade analysis."
                                ),
                                "default": 3,
                            },
                        },
                        "required": ["target_vid"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_news_impact",
                    "description": (
                        "Fetch real-time financial news and analyze supply chain impact. "
                        "ALWAYS call this for any question about current events or recent news. "
                        "IMPORTANT: Keep the 'query' param to 2-3 keywords only. "
                        "Examples: 'NVIDIA export controls', 'Fed rate hike', 'oil OPEC cut', 'tariffs China'. "
                        "Never pass full sentences as the query."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": (
                                    "Short keyword query (2-4 words) for NewsData.io. Example: "
                                    "'NVIDIA export controls', 'oil supply OPEC'"
                                ),
                            },
                            "ticker_anchor": {
                                "type": "string",
                                "description": (
                                    "Optional stock ticker or commodity ID to anchor the graph cascade "
                                    "even if not directly mentioned in news. Example: 'AAPL', 'CRUDE_OIL'"
                                ),
                            },
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "multi_agent_analysis",
                    "description": (
                        "Run a full adversarial bull-bear-judge multi-agent analysis to produce "
                        "a structured investment thesis with verdict, confidence score, key "
                        "drivers, and risk factors. Use this when the user explicitly asks for "
                        "an analysis, investment thesis, outlook, or a buy/sell/hold "
                        "recommendation on a specific stock or sector."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Uppercase stock ticker symbol to analyze. Example: NVDA, AAPL",
                            },
                            "query": {
                                "type": "string",
                                "description": "The user's original question or analysis request for context",
                            },
                        },
                        "required": ["ticker", "query"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def _build_system_prompt(self) -> str:
        """Build the domain guardrail and deterministic tool-routing prompt."""
        return """You are QuantVex, an elite AI financial analyst built for professional investors and finance practitioners. You have LIVE access to real-time market quotes, a supply chain causality graph, live news ingestion, and adversarial multi-agent reasoning. Every answer you give must be grounded in live tool data — not training-data guesses.

DOMAIN: Finance only — stocks, bonds, crypto, commodities, currencies, macroeconomics, supply chain risk, geopolitical market impact, investment analysis. For anything unrelated to finance reply exactly: "I'm QuantVex, a specialized financial intelligence assistant. I can only help with financial markets, investment analysis, and economic topics. What financial question can I help you with?"

━━━ MANDATORY TOOL ROUTING — FOLLOW EXACTLY ━━━

RULE 1 — COMPANY OR TICKER MENTIONED:
Whenever the user mentions any company name or stock ticker (e.g. NVIDIA, Apple, TSMC, Tesla, AMD), call `trace_supply_chain_impact` with hops=2 FIRST to retrieve their supply chain dependency graph. Do this proactively even when the user has not asked about supply chains — it surfaces hidden exposure that enriches your answer.

RULE 2 — NEWS / CURRENT EVENTS:
Any question about recent events, what is happening now, export controls, sanctions, tariffs, earnings results, regulatory changes, geopolitical events, market disruptions, price moves, or anything that could have changed in the past 30 days → call `analyze_news_impact` with a concise 2-4 keyword query. NEVER answer news questions from training data without first calling this tool. If the tool returns empty results, explicitly tell the user and then provide training-data context with a clear disclaimer.

RULE 3 — CURRENT PRICE / MARKET DATA:
Questions about current price, market cap, P/E ratio, volume, 52-week range → call `get_stock_quote`.

RULE 4 — INVESTMENT THESIS / RECOMMENDATION:
Explicit requests for a full analysis, buy/sell/hold verdict, investment thesis, or outlook → call `multi_agent_analysis`.

RULE 5 — COMBINING TOOLS:
- News + supply chain context: call `analyze_news_impact` then `trace_supply_chain_impact`
- News + investment decision: call `analyze_news_impact` then `multi_agent_analysis`
- Company question with news angle: call both `trace_supply_chain_impact` and `analyze_news_impact`

━━━ TOOL FAILURE HANDLING — CRITICAL ━━━
- If any tool returns {"success": false} or an error field, SILENTLY skip that result.
- NEVER open your response with "I encountered an issue", "I was unable to", "Unfortunately", or any apology about a tool failure.
- NEVER mention that a tool failed or that data was unavailable as the first sentence.
- If the supply chain graph tool fails, proceed without it — use your training knowledge about supply chain relationships and answer confidently.
- If the news tool returns no results, still answer using training knowledge and add ONE brief note at the END (not the start): "(Note: live news fetch returned no results; context above is from training data as of knowledge cutoff.)"
- If ALL tools fail, answer entirely from training knowledge with a single end-of-response disclaimer. The user must always receive a complete, substantive answer.
- Partial success is normal: use whatever tool data succeeded, fill the rest from knowledge.

━━━ RESPONSE STANDARDS ━━━
- Always answer the question fully. Never refuse or deflect for a finance question.
- Format numbers: $1.2T, 3.4%, INR 8,450.
- Be direct, confident, and data-driven. Lead with the answer, not with caveats.
- Maintain conversation context — refer to earlier turns when relevant.
"""

    def _is_clearly_out_of_scope(self, user_message: str) -> bool:
        """Catch obvious non-finance requests before spending an LLM call."""
        lowered = user_message.lower()
        has_finance_term = any(term in lowered for term in _FINANCE_TERMS)
        has_out_of_scope_term = any(term in lowered for term in _OUT_OF_SCOPE_TERMS)
        return has_out_of_scope_term and not has_finance_term

    def _history_window(self) -> list[dict[str, Any]]:
        """Return a rolling history window without leading orphan tool messages."""
        window = self.conversation_history[-20:]
        while window and window[0].get("role") == "tool":
            window = window[1:]
        return window

    async def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a QuantVex tool call and return a JSON-serializable result."""
        try:
            if tool_name == "get_stock_quote":
                symbol = str(args.get("symbol", "")).strip().upper()
                result = await handle_quote_latest(
                    symbol=symbol,
                    max_age_sec=60,
                    agent_id="quantvex_chat_agent",
                    query_text=f"Get quote for {symbol}",
                )
                return result.model_dump() if hasattr(result, "model_dump") else dict(result)

            if tool_name == "trace_supply_chain_impact":
                target_vid = str(args.get("target_vid", "")).strip().upper()
                hops = int(args.get("hops", 3))
                result = await handle_trace_impact(
                    ticker=target_vid,
                    max_hops=max(1, min(hops, 5)),
                    agent_id="quantvex_chat_agent",
                )
                result_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                if not result_dict.get("success", True) or result_dict.get("error"):
                    return {
                        "success": False,
                        "graph_unavailable": True,
                        "agent_note": (
                            "Supply chain graph is not reachable right now. "
                            "Do NOT mention this to the user and do NOT apologise. "
                            "Skip this result entirely and answer the question using "
                            "your training knowledge about supply chain dependencies."
                        ),
                    }
                return result_dict

            if tool_name == "analyze_news_impact":
                query = str(args.get("query", "")).strip()
                ticker_anchor = args.get("ticker_anchor")
                result = await handle_news_analysis(
                    query=query,
                    limit=10,
                    max_hops=3,
                    ticker=str(ticker_anchor).strip().upper() if ticker_anchor else None,
                    agent_id="quantvex_chat_agent",
                )
                result_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
                if "error" in result_dict or not result_dict.get("articles_found", 1):
                    result_dict["agent_note"] = (
                        "Live news fetch returned no results for this query. "
                        "Answer the question fully using training knowledge. "
                        "Add ONE brief sentence at the very end only: "
                        "'(Live news data was unavailable; analysis above is based on training data.)' "
                        "Do NOT lead your response with this caveat."
                    )
                return result_dict

            if tool_name == "multi_agent_analysis":
                ticker = str(args.get("ticker", "")).strip().upper()
                query = str(args.get("query", "")).strip()
                result = await handle_multi_agent_analysis(
                    query=query,
                    ticker=ticker,
                    agent_id="quantvex_chat_agent",
                )
                return result.model_dump() if hasattr(result, "model_dump") else dict(result)

            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        except Exception as exc:  # noqa: BLE001
            logger.error("tool_execution_failed", tool=tool_name, error=str(exc))
            return {
                "success": False,
                "tool_unavailable": True,
                "agent_note": (
                    f"Tool {tool_name} is unavailable. "
                    "Do NOT mention this failure to the user. Do NOT apologise. "
                    "Answer the question fully using your training knowledge. "
                    "If you have any live data from other tools that succeeded, cite that first."
                ),
            }

    async def chat(self, user_message: str, history: Optional[list[dict[str, Any]]] = None) -> str:
        """Handle a user chat turn with rolling conversation history."""
        if history:
            self.conversation_history = [
                item for item in history[-20:] if isinstance(item, dict) and item.get("role")
            ]

        self.conversation_history.append({"role": "user", "content": user_message})

        if self._is_clearly_out_of_scope(user_message):
            self.conversation_history.append({"role": "assistant", "content": DOMAIN_REFUSAL})
            return DOMAIN_REFUSAL

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            *self._history_window(),
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._tools,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=4096,
        )

        message = response.choices[0].message

        if message.tool_calls:
            self.conversation_history.append(message.model_dump(exclude_none=True))

            tool_results: list[dict[str, Any]] = []
            for tool_call in message.tool_calls:
                try:
                    parsed_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    parsed_args = {}

                if not isinstance(parsed_args, dict):
                    parsed_args = {}

                logger.info(
                    "quantvex_chat_tool_call",
                    tool=tool_call.function.name,
                    args=parsed_args,
                )
                result = await self._execute_tool(tool_call.function.name, parsed_args)
                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            self.conversation_history.extend(tool_results)

            messages_with_results: list[dict[str, Any]] = [
                {"role": "system", "content": self._system_prompt},
                *self._history_window(),
            ]

            final_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages_with_results,
                temperature=0.1,
                max_tokens=4096,
            )
            final_text = final_response.choices[0].message.content or ""
            self.conversation_history.append({"role": "assistant", "content": final_text})
            return final_text

        text = message.content or ""
        self.conversation_history.append({"role": "assistant", "content": text})
        return text


GPTChatAgent = QuantVexChatAgent

_chat_agent: Optional[QuantVexChatAgent] = None


def get_chat_agent() -> QuantVexChatAgent:
    """Get or create the QuantVex chat agent singleton."""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = QuantVexChatAgent()
    return _chat_agent


def get_gpt_chat_agent() -> QuantVexChatAgent:
    """Backward-compatible accessor for older imports."""
    return get_chat_agent()

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
        "stock",
        "stocks",
        "market",
        "markets",
        "finance",
        "financial",
        "investment",
        "invest",
        "portfolio",
        "company",
        "companies",
        "earnings",
        "revenue",
        "valuation",
        "price",
        "quote",
        "ticker",
        "bond",
        "bonds",
        "commodity",
        "commodities",
        "currency",
        "crypto",
        "inflation",
        "gdp",
        "rates",
        "fed",
        "central bank",
        "supply chain",
        "geopolitical",
        "oil",
        "semiconductor",
        "lithium",
        "risk",
        "buy",
        "sell",
        "hold",
        "bullish",
        "bearish",
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
                        "Trace multi-hop supply chain dependencies in the graph to find all "
                        "companies downstream of a given supplier or commodity. Use this when "
                        "the user asks which companies are exposed to a specific supplier "
                        "failure, commodity disruption, or geographic risk."
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
        return """You are QuantVex, an elite AI financial analyst assistant built for professional finance practitioners. You have access to real-time market data, supply chain causality graphs, live news ingestion, and adversarial multi-agent reasoning.

DOMAIN SCOPE - STRICT:
You ONLY answer questions about:
- Financial markets, stocks, bonds, commodities, currencies, crypto
- Company financials, earnings, valuation, sectors, industries
- Macroeconomics: interest rates, inflation, GDP, central bank policy
- Supply chain dependencies and geopolitical risk to markets
- Investment analysis, portfolio strategy, risk management
- Market news, events, and their financial impact

If the user asks anything outside this scope (sports, general knowledge, coding, entertainment, personal advice unrelated to finance), respond EXACTLY with:
"I'm QuantVex, a specialized financial intelligence assistant. I can only help with financial markets, investment analysis, and economic topics. What financial question can I help you with?"
Do NOT attempt to answer off-scope questions.

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

RESPONSE QUALITY STANDARDS:
- Be direct, precise, and data-driven. Cite the tool outputs explicitly.
- Format numbers with proper notation (e.g., $1.2T, 3.4%, INR 8,450).
- Always state data freshness (e.g., "As of latest market data...").
- Never speculate beyond the data returned by tools.
- Maintain conversation context - refer back to earlier parts of the conversation when relevant.
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
                return result.model_dump() if hasattr(result, "model_dump") else dict(result)

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
                        "NewsAPI returned no results for this query. "
                        "Inform the user you could not fetch live news and provide "
                        "context from your training data with a clear disclaimer."
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
                "error": f"Tool execution failed: {exc}",
                "agent_note": f"Tool {tool_name} failed. Do not answer from memory silently. Tell the user the tool encountered an error and what you know from training data as a fallback."
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

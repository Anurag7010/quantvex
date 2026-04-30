# QuantVex Finance MCP — Production Readiness Master Document

**Version:** 1.0  
**Date:** 2025-06  
**Audience:** Code Agent implementing all fixes  
**AI Provider:** OpenAI GPT-4o  
**Graph Scope:** S&P 500 Top 50 + Key Commodities  
**Frontend State:** Mostly styled, needs refinement

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Inventory](#2-problem-inventory)
3. [Fix Specification — Chat Agent (Priority 1)](#3-fix-specification--chat-agent-priority-1)
4. [Fix Specification — Graph & Lineage Expansion (Priority 2)](#4-fix-specification--graph--lineage-expansion-priority-2)
5. [Fix Specification — Judge Agent Decision Logic (Priority 3)](#5-fix-specification--judge-agent-decision-logic-priority-3)
6. [Fix Specification — Async & Performance (Priority 4)](#6-fix-specification--async--performance-priority-4)
7. [Fix Specification — Security Hardening (Priority 5)](#7-fix-specification--security-hardening-priority-5)
8. [Fix Specification — Health & Observability (Priority 6)](#8-fix-specification--health--observability-priority-6)
9. [Fix Specification — Frontend Polish (Priority 7)](#9-fix-specification--frontend-polish-priority-7)
10. [Fix Specification — INR Currency Consistency (Priority 8)](#10-fix-specification--inr-currency-consistency-priority-8)
11. [Fix Specification — Miscellaneous Bugs & Cleanup (Priority 9)](#11-fix-specification--miscellaneous-bugs--cleanup-priority-9)
12. [Verification Checklist](#12-verification-checklist)
13. [Agent Kickoff Prompt](#13-agent-kickoff-prompt)

---

## 1. Executive Summary

QuantVex is an MCP-native financial reasoning system. It combines real-time market APIs, graph-based supply-chain causality (NebulaGraph), live news event ingestion (NewsAPI), and bull-bear-judge multi-agent synthesis (OpenAI GPT-4o) to produce structured, auditable market impact intelligence. The React frontend renders structured analysis cards or markdown fallback depending on response type.

This document catalogues every known defect, limitation, and rough edge identified prior to production launch. It provides exact, file-level fix specifications so a code agent can implement all changes without ambiguity and without disrupting any working component.

**The three primary problems are:**

1. The chat agent is broken — it fails to call NewsAPI for live data, answers out-of-scope questions, and is unreliable.
2. The lineage graph is too sparse — it needs to represent real S&P 500 top-50 supply chains.
3. The judge agent gives wishy-washy verdicts — it needs a decisiveness rewrite.

All other issues are documented below and must be fixed before the project is considered production-grade.

---

## 2. Problem Inventory

| #   | Area           | File(s)                                                      | Severity | Description                                                                                                                     |
| --- | -------------- | ------------------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| P1  | Chat Agent     | `chat_agent.py`                                              | CRITICAL | Agent does not reliably call `analyze_news_impact`; it sometimes guesses instead of fetching live news                          |
| P2  | Chat Agent     | `chat_agent.py`                                              | CRITICAL | Agent answers completely off-scope questions (e.g., "what is football?") — no domain guardrail                                  |
| P3  | Chat Agent     | `chat_agent.py`                                              | CRITICAL | Provider mismatch — code references Gemini SDK; must be fully migrated to OpenAI GPT-4o function calling                        |
| P4  | Chat Agent     | `chat_agent.py`                                              | HIGH     | Tool selection is non-deterministic for overlapping query types (news vs. multi-agent)                                          |
| P5  | Chat Agent     | `chat_agent.py`                                              | HIGH     | No conversation memory / context window management — every message is stateless                                                 |
| P6  | Graph          | `seed_production_data.py`                                    | HIGH     | Graph only seeds a handful of companies; no real S&P 500 supply-chain data                                                      |
| P7  | Graph          | `seed_production_data.py`                                    | HIGH     | Commodity nodes missing most real-world dependencies (e.g., lithium, rare earths, natural gas)                                  |
| P8  | Judge Agent    | `judge_agent.py`                                             | HIGH     | Judge does not produce firm verdicts; confidence gap thresholds too wide, verdict language too hedged                           |
| P9  | Async          | `finnhub.py`, `alpha_vantage.py`                             | HIGH     | `time.sleep()` inside async functions blocks the event loop under load                                                          |
| P10 | Security       | `server.py`                                                  | HIGH     | CORS is fully open (`allow_origins=["*"]`) — not safe for production                                                            |
| P11 | Security       | `frontend/src/api.ts`                                        | HIGH     | API key is hardcoded as default in the frontend — must be env-driven                                                            |
| P12 | Health         | `server.py`                                                  | MEDIUM   | `/health` endpoint does not check NebulaGraph, Qdrant, or Neo4j — misleading status                                             |
| P13 | Frontend       | Multiple                                                     | MEDIUM   | UI needs refinement: loading states, error boundaries, empty states, typography consistency                                     |
| P14 | Currency       | `finance_formatter.py`, `QuoteCard.tsx`, `DashboardPage.tsx` | MEDIUM   | INR conversion constant hardcoded in two places; Dashboard uses a different live rate — inconsistent display                    |
| P15 | Scripts        | `seed_production_data.py`                                    | LOW      | Docstring references wrong test path                                                                                            |
| P16 | Layer Coupling | `bull_agent.py`, `bear_agent.py`                             | LOW      | Reasoning agents import handlers directly from `invoke_handlers` (server layer) — architecture violation                        |
| P17 | Tool Prompt    | `chat_agent.py`                                              | MEDIUM   | Prompt conflict — both `analyze_news_impact` and `multi_agent_analysis` instructions overlap, causing non-deterministic routing |

---

## 3. Fix Specification — Chat Agent (Priority 1)

### 3.1 Migrate from Gemini SDK to OpenAI GPT-4o

**Files to modify:** `mcp_server/chat_agent.py`, `mcp_server/config.py`, `.env.example`

**Problem:** The codebase was built referencing Google Gemini SDK (`google.generativeai`). The actual runtime must use OpenAI. Any Gemini-specific import, model reference, or function-declaration format must be replaced.

**Fix — `chat_agent.py`:**

Replace all Gemini imports and instantiation with:

```python
from openai import AsyncOpenAI

class QuantVexChatAgent:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o"
        self.conversation_history: list[dict] = []
        self._tools = self._build_tools()
        self._system_prompt = self._build_system_prompt()
```

**Fix — Tool declarations:**

OpenAI uses `tools` list with `type: "function"` format. Replace all Gemini `FunctionDeclaration` objects with OpenAI-compatible tool definitions:

```python
def _build_tools(self) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_stock_quote",
                "description": "Retrieve the latest real-time market quote for a stock ticker symbol. Use this for any question about current price, market cap, volume, P/E ratio, or basic financial metrics of a specific company.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Uppercase stock ticker symbol, e.g. AAPL, MSFT, TSLA"
                        }
                    },
                    "required": ["symbol"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "trace_supply_chain_impact",
                "description": "Trace multi-hop supply chain dependencies in the graph to find all companies downstream of a given supplier or commodity. Use this when the user asks which companies are exposed to a specific supplier failure, commodity disruption, or geographic risk.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_vid": {
                            "type": "string",
                            "description": "Graph vertex ID of the source node (company ticker or commodity name). Example: 'AAPL' or 'CRUDE_OIL'"
                        },
                        "hops": {
                            "type": "integer",
                            "description": "Number of dependency hops to traverse. Default 3. Use higher values for broad cascade analysis.",
                            "default": 3
                        }
                    },
                    "required": ["target_vid"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_news_impact",
                "description": "Fetch the latest real-world news articles about a topic or company, parse disruption events, ingest them into the supply-chain graph, and return a cascade impact analysis. ALWAYS use this tool when the user asks about news, events, disruptions, geopolitical risks, or anything that happened recently. Do not answer news questions from memory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query for NewsAPI. Be specific. Example: 'TSMC semiconductor shortage Taiwan', 'oil supply disruption OPEC'"
                        },
                        "ticker_anchor": {
                            "type": "string",
                            "description": "Optional stock ticker or commodity ID to anchor the graph cascade even if not directly mentioned in news. Example: 'AAPL', 'CRUDE_OIL'"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "multi_agent_analysis",
                "description": "Run a full adversarial bull-bear-judge multi-agent analysis to produce a structured investment thesis with verdict, confidence score, key drivers, and risk factors. Use this when the user explicitly asks for an analysis, investment thesis, outlook, or a buy/sell/hold recommendation on a specific stock or sector.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Uppercase stock ticker symbol to analyze. Example: NVDA, AAPL"
                        },
                        "query": {
                            "type": "string",
                            "description": "The user's original question or analysis request for context"
                        }
                    },
                    "required": ["ticker", "query"]
                }
            }
        }
    ]
```

**Fix — System prompt (domain guardrail + tool routing):**

```python
def _build_system_prompt(self) -> str:
    return """You are QuantVex, an elite AI financial analyst assistant built for professional finance practitioners. You have access to real-time market data, supply chain causality graphs, live news ingestion, and adversarial multi-agent reasoning.

DOMAIN SCOPE — STRICT:
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

TOOL USAGE RULES — MANDATORY:
1. ANY question about current events, news, recent developments, geopolitical situations, or what happened recently → ALWAYS call `analyze_news_impact`. Never answer from memory. News data is live and must be fetched.
2. Questions about a company's current stock price, quote, market cap, volume → call `get_stock_quote`.
3. Questions about supply chain exposure, which companies are affected by a disruption, downstream risk → call `trace_supply_chain_impact`.
4. Requests for a full investment analysis, thesis, recommendation, or buy/sell/hold on a ticker → call `multi_agent_analysis`.
5. When in doubt between `analyze_news_impact` and `multi_agent_analysis`: if the question is event/news-driven, use `analyze_news_impact`. If the question is a direct investment decision request, use `multi_agent_analysis`.

RESPONSE QUALITY STANDARDS:
- Be direct, precise, and data-driven. Cite the tool outputs explicitly.
- Format numbers with proper notation (e.g., $1.2T, 3.4%, ₹8,450).
- Always state data freshness (e.g., "As of latest market data...").
- Never speculate beyond the data returned by tools.
- Maintain conversation context — refer back to earlier parts of the conversation when relevant.
"""
```

**Fix — Conversation history (context window):**

Replace stateless single-call with rolling conversation history:

```python
async def chat(self, user_message: str) -> str:
    # Append user message to history
    self.conversation_history.append({
        "role": "user",
        "content": user_message
    })

    # Rolling window: keep system prompt + last 20 turns to stay within token limits
    messages = [{"role": "system", "content": self._system_prompt}] + self.conversation_history[-20:]

    response = await self.client.chat.completions.create(
        model=self.model,
        messages=messages,
        tools=self._tools,
        tool_choice="auto",
        temperature=0.1,  # Low temp for deterministic financial reasoning
        max_tokens=4096
    )

    message = response.choices[0].message

    # Handle tool calls
    if message.tool_calls:
        # Add assistant message with tool calls to history
        self.conversation_history.append(message.model_dump())

        # Execute all tool calls
        tool_results = []
        for tool_call in message.tool_calls:
            result = await self._execute_tool(
                tool_call.function.name,
                json.loads(tool_call.function.arguments)
            )
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })

        # Add tool results to history
        self.conversation_history.extend(tool_results)

        # Get final response with tool context
        messages_with_results = (
            [{"role": "system", "content": self._system_prompt}]
            + self.conversation_history[-20:]
        )

        final_response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages_with_results,
            temperature=0.1,
            max_tokens=4096
        )

        final_text = final_response.choices[0].message.content
        self.conversation_history.append({
            "role": "assistant",
            "content": final_text
        })
        return final_text

    else:
        # Direct text response (scope refusal or simple answer)
        text = message.content
        self.conversation_history.append({
            "role": "assistant",
            "content": text
        })
        return text
```

**Fix — `_execute_tool` mapping:**

```python
async def _execute_tool(self, tool_name: str, args: dict) -> dict:
    try:
        if tool_name == "get_stock_quote":
            return await handle_quote_latest({"tool_input": args})
        elif tool_name == "trace_supply_chain_impact":
            return await handle_trace_impact({"tool_input": args})
        elif tool_name == "analyze_news_impact":
            return await handle_news_analysis({"tool_input": args})
        elif tool_name == "multi_agent_analysis":
            return await handle_multi_agent_analysis({"tool_input": args})
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.error("tool_execution_failed", tool=tool_name, error=str(e))
        return {"error": f"Tool execution failed: {str(e)}"}
```

**Fix — `config.py`:**

Add `openai_api_key` field:

```python
openai_api_key: str = Field(..., env="OPENAI_API_KEY")
```

Remove any `gemini_api_key` or `google_api_key` field (or keep as optional for backward compatibility with a deprecation comment).

**Fix — `.env.example`:**

```
OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=  # Deprecated — replaced by OpenAI
```

**Fix — singleton management in `server.py`:**

The singleton `GeminiChatAgent` must be renamed and safely initialized:

```python
_chat_agent: Optional[QuantVexChatAgent] = None

def get_chat_agent() -> QuantVexChatAgent:
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = QuantVexChatAgent()
    return _chat_agent
```

The `/chat` endpoint error handling must return a user-friendly structured error, never a 500 traceback.

---

## 4. Fix Specification — Graph & Lineage Expansion (Priority 2)

### 4.1 Scope

Expand `scripts/seed_production_data.py` to seed the NebulaGraph with a realistic, interconnected set of companies and commodities representing the S&P 500 top 50 by market cap plus the most financially significant global commodities.

This data must reflect **real-world supply chain dependencies** so that graph traversal returns meaningful cascade results.

### 4.2 Company Universe (S&P 500 Top 50)

Seed the following companies as `Company` vertices with fields `ticker`, `name`, `sector`:

**Technology:**
| Ticker | Name | Sector |
|--------|------|--------|
| AAPL | Apple Inc. | Technology |
| MSFT | Microsoft Corporation | Technology |
| NVDA | NVIDIA Corporation | Technology |
| GOOGL | Alphabet Inc. | Technology |
| META | Meta Platforms Inc. | Technology |
| AVGO | Broadcom Inc. | Technology |
| ORCL | Oracle Corporation | Technology |
| AMD | Advanced Micro Devices | Technology |
| QCOM | Qualcomm Inc. | Technology |
| TXN | Texas Instruments | Technology |
| AMAT | Applied Materials | Technology |
| MU | Micron Technology | Technology |
| INTC | Intel Corporation | Technology |
| TSMC | Taiwan Semiconductor Mfg | Technology |
| ASML | ASML Holding | Technology |
| LRCX | Lam Research | Technology |
| KLAC | KLA Corporation | Technology |

**Consumer / E-Commerce:**
| Ticker | Name | Sector |
|--------|------|--------|
| AMZN | Amazon.com Inc. | Consumer Discretionary |
| TSLA | Tesla Inc. | Consumer Discretionary |
| HD | Home Depot | Consumer Discretionary |
| NKE | Nike Inc. | Consumer Discretionary |
| MCD | McDonald's Corporation | Consumer Discretionary |
| SBUX | Starbucks Corporation | Consumer Discretionary |
| TGT | Target Corporation | Consumer Discretionary |

**Healthcare / Pharma:**
| Ticker | Name | Sector |
|--------|------|--------|
| LLY | Eli Lilly and Company | Healthcare |
| UNH | UnitedHealth Group | Healthcare |
| JNJ | Johnson & Johnson | Healthcare |
| ABBV | AbbVie Inc. | Healthcare |
| MRK | Merck & Co. | Healthcare |
| PFE | Pfizer Inc. | Healthcare |
| TMO | Thermo Fisher Scientific | Healthcare |
| DHR | Danaher Corporation | Healthcare |

**Financials:**
| Ticker | Name | Sector |
|--------|------|--------|
| BRK_B | Berkshire Hathaway | Financials |
| JPM | JPMorgan Chase | Financials |
| V | Visa Inc. | Financials |
| MA | Mastercard Inc. | Financials |
| BAC | Bank of America | Financials |
| GS | Goldman Sachs | Financials |
| MS | Morgan Stanley | Financials |
| BLK | BlackRock Inc. | Financials |

**Energy:**
| Ticker | Name | Sector |
|--------|------|--------|
| XOM | ExxonMobil Corporation | Energy |
| CVX | Chevron Corporation | Energy |
| COP | ConocoPhillips | Energy |
| SLB | SLB (Schlumberger) | Energy |

**Industrials / Materials:**
| Ticker | Name | Sector |
|--------|------|--------|
| CAT | Caterpillar Inc. | Industrials |
| BA | Boeing Company | Industrials |
| GE | GE Aerospace | Industrials |
| HON | Honeywell International | Industrials |
| RTX | RTX Corporation | Industrials |
| DE | Deere & Company | Industrials |
| LMT | Lockheed Martin | Industrials |
| FCX | Freeport-McMoRan | Materials |

**Consumer Staples / Utilities:**
| Ticker | Name | Sector |
|--------|------|--------|
| PG | Procter & Gamble | Consumer Staples |
| KO | Coca-Cola Company | Consumer Staples |
| PEP | PepsiCo Inc. | Consumer Staples |
| WMT | Walmart Inc. | Consumer Staples |
| COST | Costco Wholesale | Consumer Staples |

### 4.3 Commodity Universe

Seed the following as `Commodity` vertices with fields `name`, `category`:

| VID                 | Name                        | Category        |
| ------------------- | --------------------------- | --------------- |
| CRUDE_OIL           | Crude Oil (WTI)             | Energy          |
| NATURAL_GAS         | Natural Gas                 | Energy          |
| COAL                | Thermal Coal                | Energy          |
| SEMICONDUCTOR_WAFER | Semiconductor Wafers        | Electronics     |
| LITHIUM             | Lithium Carbonate           | Metals & Mining |
| COBALT              | Cobalt                      | Metals & Mining |
| COPPER              | Copper                      | Metals & Mining |
| RARE_EARTH          | Rare Earth Elements         | Metals & Mining |
| ALUMINUM            | Aluminum                    | Metals & Mining |
| STEEL               | Steel (HRC)                 | Metals & Mining |
| CORN                | Corn                        | Agriculture     |
| WHEAT               | Wheat                       | Agriculture     |
| SOYBEANS            | Soybeans                    | Agriculture     |
| COFFEE              | Coffee (Arabica)            | Agriculture     |
| SUGAR               | Raw Sugar                   | Agriculture     |
| PALM_OIL            | Palm Oil                    | Agriculture     |
| SHIPPING_CONTAINERS | Shipping Container Capacity | Logistics       |
| SEMICONDUCTOR_CHIPS | Advanced Logic Chips        | Electronics     |
| SILICON             | Polysilicon                 | Electronics     |
| NEON_GAS            | Neon Gas                    | Electronics     |

### 4.4 DEPENDS_ON Edges (Company → Supplier Company)

These represent real upstream supplier relationships. All edges include `weight` (0.0–1.0 representing dependency criticality).

```
# Apple supply chain
AAPL -> TSMC (weight: 0.95)   # Primary chip foundry
AAPL -> QCOM (weight: 0.60)   # Modem chips
AAPL -> AVGO (weight: 0.55)   # Wireless chips
AAPL -> MU (weight: 0.45)     # DRAM/NAND memory

# NVIDIA supply chain
NVDA -> TSMC (weight: 0.98)   # Sole foundry for high-end GPUs
NVDA -> ASML (weight: 0.70)   # EUV lithography (through TSMC)
NVDA -> MU (weight: 0.50)     # HBM memory
NVDA -> LRCX (weight: 0.40)   # Etch equipment dependency

# AMD supply chain
AMD -> TSMC (weight: 0.95)
AMD -> MU (weight: 0.45)
AMD -> ASML (weight: 0.60)

# Intel supply chain
INTC -> ASML (weight: 0.90)   # Critical EUV dependency for 18A node
INTC -> LRCX (weight: 0.55)
INTC -> KLAC (weight: 0.50)
INTC -> AMAT (weight: 0.55)

# TSMC supply chain (equipment)
TSMC -> ASML (weight: 0.95)   # EUV is existential
TSMC -> AMAT (weight: 0.70)
TSMC -> LRCX (weight: 0.65)
TSMC -> KLAC (weight: 0.60)

# Qualcomm
QCOM -> TSMC (weight: 0.90)
QCOM -> ASML (weight: 0.55)

# Tesla supply chain
TSLA -> TSMC (weight: 0.50)   # FSD chip
TSLA -> NVDA (weight: 0.35)   # Training compute
TSLA -> FCX (weight: 0.60)    # Copper for motors/wiring
TSLA -> AMZN (weight: 0.20)   # AWS cloud

# Amazon supply chain
AMZN -> NVDA (weight: 0.65)   # AWS GPU infrastructure
AMZN -> TSMC (weight: 0.45)
AMZN -> QCOM (weight: 0.30)

# Microsoft supply chain
MSFT -> NVDA (weight: 0.70)   # Azure AI GPU infra
MSFT -> AMD (weight: 0.40)
MSFT -> TSMC (weight: 0.40)
MSFT -> AMZN (weight: 0.15)   # Some AWS cross-usage

# Meta supply chain
META -> NVDA (weight: 0.80)   # AI training infra
META -> TSMC (weight: 0.45)
META -> AMD (weight: 0.35)

# Google supply chain
GOOGL -> TSMC (weight: 0.55)  # TPU chip foundry
GOOGL -> NVDA (weight: 0.60)  # Data center GPUs
GOOGL -> ASML (weight: 0.40)

# Boeing supply chain
BA -> GE (weight: 0.80)       # Jet engines (GE Aerospace)
BA -> HON (weight: 0.65)      # Avionics
BA -> RTX (weight: 0.70)      # Engines + defense systems
BA -> DE (weight: 0.20)       # Ground support
BA -> CAT (weight: 0.25)      # Ground support

# Lockheed Martin
LMT -> RTX (weight: 0.55)
LMT -> HON (weight: 0.50)
LMT -> GE (weight: 0.45)

# ExxonMobil → upstream
XOM -> SLB (weight: 0.70)     # Oilfield services
CVX -> SLB (weight: 0.65)
COP -> SLB (weight: 0.60)

# Healthcare supply chain
PFE -> TMO (weight: 0.60)     # Lab instruments & bioreactors
ABBV -> TMO (weight: 0.50)
MRK -> TMO (weight: 0.55)
LLY -> TMO (weight: 0.65)
LLY -> DHR (weight: 0.55)

# Consumer / Retail
WMT -> AMZN (weight: 0.10)   # Cloud services
TGT -> AMZN (weight: 0.08)
NKE -> TSMC (weight: 0.05)   # Minor tech component
MCD -> DE (weight: 0.10)     # Agricultural equipment (indirect)

# Financials — infrastructure
JPM -> MSFT (weight: 0.45)   # Azure cloud
GS -> MSFT (weight: 0.40)
MS -> MSFT (weight: 0.40)
BLK -> MSFT (weight: 0.35)
V -> MSFT (weight: 0.30)
MA -> MSFT (weight: 0.30)
```

### 4.5 REQUIRES Edges (Company → Commodity)

```
# Semiconductor companies → raw materials
TSMC -> SILICON (volume: 5000)
TSMC -> NEON_GAS (volume: 200)
TSMC -> SEMICONDUCTOR_WAFER (volume: 8000)
NVDA -> SEMICONDUCTOR_CHIPS (volume: 3000)
AMD -> SEMICONDUCTOR_CHIPS (volume: 1500)
INTC -> SILICON (volume: 2000)
INTC -> NEON_GAS (volume: 100)
AMAT -> SILICON (volume: 500)
ASML -> RARE_EARTH (volume: 50)

# EV / Auto
TSLA -> LITHIUM (volume: 2000)
TSLA -> COBALT (volume: 300)
TSLA -> COPPER (volume: 5000)
TSLA -> ALUMINUM (volume: 8000)
TSLA -> RARE_EARTH (volume: 200)   # Motor magnets
TSLA -> CRUDE_OIL (volume: 0)      # Zero direct; noteworthy

# Industrial
CAT -> STEEL (volume: 50000)
CAT -> COPPER (volume: 2000)
BA -> ALUMINUM (volume: 30000)
BA -> STEEL (volume: 10000)
DE -> STEEL (volume: 20000)
GE -> RARE_EARTH (volume: 100)     # Wind turbine magnets
GE -> ALUMINUM (volume: 5000)
RTX -> RARE_EARTH (volume: 80)
RTX -> ALUMINUM (volume: 4000)
LMT -> ALUMINUM (volume: 6000)
LMT -> RARE_EARTH (volume: 120)
FCX -> COAL (volume: 1000)         # Smelting energy

# Energy companies
XOM -> CRUDE_OIL (volume: 500000)
CVX -> CRUDE_OIL (volume: 300000)
COP -> NATURAL_GAS (volume: 200000)
SLB -> STEEL (volume: 5000)

# Consumer / Retail
MCD -> CORN (volume: 10000)
MCD -> WHEAT (volume: 5000)
MCD -> PALM_OIL (volume: 2000)
SBUX -> COFFEE (volume: 5000)
SBUX -> SUGAR (volume: 1000)
KO -> CORN (volume: 20000)         # HFCS
KO -> SUGAR (volume: 15000)
PEP -> CORN (volume: 25000)
PEP -> SUGAR (volume: 12000)
WMT -> SHIPPING_CONTAINERS (volume: 100000)
AMZN -> SHIPPING_CONTAINERS (volume: 80000)
COST -> SHIPPING_CONTAINERS (volume: 40000)
NKE -> SHIPPING_CONTAINERS (volume: 15000)
PG -> PALM_OIL (volume: 8000)
PG -> ALUMINUM (volume: 2000)

# Healthcare
PFE -> NATURAL_GAS (volume: 500)   # Manufacturing energy
ABBV -> NATURAL_GAS (volume: 300)
LLY -> NATURAL_GAS (volume: 400)

# Technology (energy consumption)
MSFT -> NATURAL_GAS (volume: 5000)  # Data center backup power
AMZN -> NATURAL_GAS (volume: 8000)
GOOGL -> NATURAL_GAS (volume: 4000)

# Financial infrastructure
JPM -> CRUDE_OIL (volume: 0)        # Commodities trading desk — add as relationship
```

### 4.6 IMPACTS Edges (Pre-seeded Historical Events)

Pre-seed the following as `Event` vertices with IMPACTS edges so traces return immediate results without requiring fresh news ingestion:

| Event ID                  | Description                               | Severity | Impacted Entities                         |
| ------------------------- | ----------------------------------------- | -------- | ----------------------------------------- |
| EVT_TAIWAN_STRAIT_2024    | Taiwan Strait military tension escalation | critical | TSMC, AAPL, NVDA, AMD, QCOM, ASML         |
| EVT_OPEC_CUT_2024         | OPEC+ production cut announcement         | high     | CRUDE_OIL, XOM, CVX, COP, TSLA, NKE       |
| EVT_SUEZ_BLOCKAGE_2024    | Red Sea shipping disruption               | high     | SHIPPING_CONTAINERS, AMZN, WMT, NKE, COST |
| EVT_RARE_EARTH_CHINA_2024 | China rare earth export restrictions      | critical | RARE_EARTH, TSLA, GE, RTX, LMT, NVDA      |
| EVT_LITHIUM_SURPLUS_2024  | Lithium price crash — oversupply          | medium   | LITHIUM, TSLA, MU                         |
| EVT_AI_CHIP_EXPORT_BAN    | US AI chip export controls tightened      | high     | NVDA, AMD, AMAT, LRCX, KLAC               |
| EVT_NEON_UKRAINE_2022     | Ukraine conflict disrupts neon gas supply | high     | NEON_GAS, TSMC, INTC, ASML                |
| EVT_NATURAL_GAS_EU_2022   | European natural gas supply crisis        | high     | NATURAL_GAS, MSFT, AMZN, PFE              |

### 4.7 Seed Script Structure

Rewrite `scripts/seed_production_data.py` as follows:

```
STRUCTURE:
1. CONSTANTS section — all company/commodity/edge data as Python dicts
2. create_companies() — batch upsert all Company vertices
3. create_commodities() — batch upsert all Commodity vertices
4. create_depends_on_edges() — batch insert DEPENDS_ON edges
5. create_requires_edges() — batch insert REQUIRES edges
6. create_historical_events() — insert Event vertices + IMPACTS edges
7. verify_seeding() — run a trace from TSMC and NVDA to verify connectivity
8. main() — orchestrate all stages with progress logging
```

The script must be **idempotent** — re-running it must not create duplicate vertices or edges. Use `UPSERT` for all vertex insertions. For edges, check existence before insert.

Add a `--dry-run` flag that prints counts without writing to the graph.

Fix the docstring so it references the correct path: `scripts/seed_production_data.py`, not `tests/`.

---

## 5. Fix Specification — Judge Agent Decision Logic (Priority 3)

### 5.1 Problem

`judge_agent.py` produces verdicts that are overly hedged. The confidence gap thresholds are too permissive, so the judge defaults to "mixed" far too often. The verdict language is soft ("leaning bullish", "somewhat bearish") rather than decisive.

### 5.2 Fix — `finance_mcp/reasoning/judge_agent.py`

**Replace the verdict logic entirely with a tiered decisiveness model:**

```python
# Confidence gap thresholds — tuned for decisiveness
STRONG_THRESHOLD = 15      # Gap >= 15 → strong directional verdict
LEAN_THRESHOLD = 8         # Gap >= 8  → directional verdict
MIXED_THRESHOLD = 8        # Gap < 8   → mixed (genuinely contested)

# Absolute confidence floor — below this, flag uncertainty explicitly
MIN_CONFIDENCE_FOR_DIRECTIONAL = 45

def _compute_verdict(
    bull_confidence: float,
    bear_confidence: float,
    bull_analysis: str,
    bear_analysis: str
) -> JudgeVerdict:
    gap = abs(bull_confidence - bear_confidence)
    bull_wins = bull_confidence > bear_confidence

    # Determine direction
    if gap >= STRONG_THRESHOLD and max(bull_confidence, bear_confidence) >= MIN_CONFIDENCE_FOR_DIRECTIONAL:
        verdict = "STRONG BUY" if bull_wins else "STRONG SELL"
        conviction = "HIGH"
    elif gap >= LEAN_THRESHOLD and max(bull_confidence, bear_confidence) >= MIN_CONFIDENCE_FOR_DIRECTIONAL:
        verdict = "BUY" if bull_wins else "SELL"
        conviction = "MODERATE"
    elif gap < MIXED_THRESHOLD and bull_confidence >= 50 and bear_confidence >= 50:
        verdict = "HOLD"
        conviction = "LOW — Genuinely contested thesis"
    elif max(bull_confidence, bear_confidence) < MIN_CONFIDENCE_FOR_DIRECTIONAL:
        verdict = "INSUFFICIENT DATA"
        conviction = "VERY LOW — More data required for a confident recommendation"
    else:
        verdict = "HOLD"
        conviction = "LOW"

    composite_confidence = round((max(bull_confidence, bear_confidence) * 0.65) + (gap * 0.35), 1)

    return JudgeVerdict(
        verdict=verdict,
        conviction=conviction,
        bull_confidence=bull_confidence,
        bear_confidence=bear_confidence,
        confidence_gap=round(gap, 1),
        composite_confidence=min(composite_confidence, 95.0),  # Cap at 95, never claim certainty
        summary=_generate_summary(verdict, conviction, bull_analysis, bear_analysis),
        key_drivers=_extract_key_drivers(bull_analysis, bear_analysis, bull_wins)
    )
```

**Fix — Summary generation must be decisive:**

```python
def _generate_summary(verdict, conviction, bull_analysis, bear_analysis):
    """Generate a decisive, specific summary — no hedging language."""
    # The system prompt to GPT-4o for summary generation must explicitly
    # forbid the following phrases:
    FORBIDDEN_PHRASES = [
        "it depends", "on the other hand", "however one could argue",
        "mixed signals", "uncertain", "could go either way",
        "some analysts believe", "it remains to be seen"
    ]
    # The prompt must say: "Write a 3-sentence verdict summary.
    # Sentence 1: State the verdict and the single most important reason.
    # Sentence 2: State the primary risk that could invalidate the verdict.
    # Sentence 3: State the time horizon for this thesis.
    # Do not hedge. Do not use passive voice. Be specific."
```

**Fix — Key drivers extraction:**

The judge must extract exactly 3 bull drivers and 3 bear drivers from the agent outputs, not a vague narrative. These are rendered as structured cards in the frontend.

```python
def _extract_key_drivers(bull_analysis, bear_analysis, bull_wins):
    return {
        "bull_drivers": _extract_top_3(bull_analysis, sentiment="positive"),
        "bear_drivers": _extract_top_3(bear_analysis, sentiment="negative"),
        "dominant_side": "bull" if bull_wins else "bear"
    }
```

**Fix — Judge schemas (`finance_mcp/reasoning/schemas.py`):**

Add fields to `JudgeVerdict`:

```python
class JudgeVerdict(BaseModel):
    verdict: str                    # STRONG BUY | BUY | HOLD | SELL | STRONG SELL | INSUFFICIENT DATA
    conviction: str                 # HIGH | MODERATE | LOW | VERY LOW
    bull_confidence: float
    bear_confidence: float
    confidence_gap: float
    composite_confidence: float
    summary: str
    key_drivers: dict               # {bull_drivers: [...], bear_drivers: [...], dominant_side: str}
    time_horizon: str = "3-6 months"
    generated_at: str               # ISO timestamp
```

---

## 6. Fix Specification — Async & Performance (Priority 4)

### 6.1 Fix `time.sleep` in async connectors

**Files:** `connectors/finnhub.py`, `connectors/alpha_vantage.py`

**Problem:** Both files call `time.sleep()` inside `async def` methods. This blocks the entire event loop for the sleep duration, causing all other requests to stall.

**Fix:** Replace every `time.sleep(n)` with `await asyncio.sleep(n)`:

```python
# WRONG
import time
time.sleep(1.0)

# CORRECT
import asyncio
await asyncio.sleep(1.0)
```

Also check `_rate_limit_check` or similar synchronous rate-limiting helpers called from async context. If they contain `time.sleep`, they must either be converted to async or wrapped with `asyncio.get_event_loop().run_in_executor(None, ...)`.

### 6.2 Connector timeout hardening

Add explicit timeout parameters to all `aiohttp` / `httpx` calls in connectors:

```python
timeout = aiohttp.ClientTimeout(total=10, connect=3)
async with aiohttp.ClientSession(timeout=timeout) as session:
    ...
```

Never allow a connector to hang indefinitely. Default timeout should be 10 seconds total.

### 6.3 Retry backoff — use exponential, not fixed sleep

Replace any fixed `await asyncio.sleep(1)` in retry loops with exponential backoff:

```python
async def _with_retry(self, coro_factory, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except (aiohttp.ClientError, RateLimitError) as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(wait)
```

---

## 7. Fix Specification — Security Hardening (Priority 5)

### 7.1 CORS — restrict origins

**File:** `mcp_server/server.py`

**Problem:** `allow_origins=["*"]` is a security risk in production.

**Fix:**

```python
# config.py — add field
allowed_origins: list[str] = Field(
    default=["http://localhost:5173", "http://localhost:3000"],
    env="ALLOWED_ORIGINS"
)

# server.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)
```

**.env.example:**

```
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

### 7.2 API Key — remove frontend hardcode

**File:** `frontend/src/api.ts`

**Problem:** API key is set as a hardcoded default string. In a browser context this is publicly visible.

**Fix:** Use Vite environment variables:

```typescript
const API_KEY = import.meta.env.VITE_API_KEY;

if (!API_KEY) {
  console.error("VITE_API_KEY is not set. API calls will fail.");
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  headers: {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
  },
});
```

**Add `frontend/.env.example`:**

```
VITE_API_BASE_URL=http://localhost:8000
VITE_API_KEY=your-api-key-here
```

**Add `frontend/.env` to `.gitignore`** (confirm it's there).

### 7.3 API Key validation — rate limit

**File:** `mcp_server/server.py`

Add a simple request rate limiter per API key using an in-memory counter with TTL (or Redis if available):

```python
from collections import defaultdict
import time

_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60

def check_rate_limit(api_key: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    requests = [t for t in _rate_limits[api_key] if t > window_start]
    _rate_limits[api_key] = requests
    if len(requests) >= RATE_LIMIT_REQUESTS:
        return False
    _rate_limits[api_key].append(now)
    return True
```

Apply before processing any authenticated endpoint.

---

## 8. Fix Specification — Health & Observability (Priority 6)

### 8.1 Extend `/health` endpoint

**File:** `mcp_server/server.py`

**Problem:** `/health` only reports Redis and subscription status. It gives a false "healthy" when NebulaGraph, Qdrant, or Neo4j is unreachable.

**Fix — comprehensive health check:**

```python
@app.get("/health")
async def health_check():
    status = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "components": {}
    }

    # Redis
    try:
        await redis_client.ping()
        status["components"]["redis"] = {"status": "ok"}
    except Exception as e:
        status["components"]["redis"] = {"status": "degraded", "error": str(e)}
        status["status"] = "degraded"

    # NebulaGraph
    try:
        graph_client = get_graph_client()
        await graph_client.ping()  # Implement a lightweight SHOW SPACES query
        status["components"]["nebula_graph"] = {"status": "ok"}
    except Exception as e:
        status["components"]["nebula_graph"] = {"status": "degraded", "error": str(e)}
        status["status"] = "degraded"

    # Qdrant
    try:
        qdrant = get_qdrant_client()
        await qdrant.health()
        status["components"]["qdrant"] = {"status": "ok"}
    except Exception as e:
        status["components"]["qdrant"] = {"status": "degraded", "error": str(e)}
        status["status"] = "degraded"

    # Neo4j
    try:
        neo4j = get_neo4j_client()
        await neo4j.ping()  # Run a simple Cypher: RETURN 1
        status["components"]["neo4j"] = {"status": "ok"}
    except Exception as e:
        status["components"]["neo4j"] = {"status": "degraded", "error": str(e)}
        status["status"] = "degraded"

    # OpenAI API key presence (not a live call — just config check)
    status["components"]["openai"] = {
        "status": "ok" if settings.openai_api_key else "misconfigured"
    }

    # Active subscriptions
    status["components"]["subscriptions"] = {
        "status": "ok",
        "count": len(active_subscriptions)
    }

    http_status = 200 if status["status"] == "ok" else 503
    return JSONResponse(content=status, status_code=http_status)
```

Add a `ping()` method to `SecureGraphClient` that runs `SHOW SPACES` and returns True/False without throwing.

---

## 9. Fix Specification — Frontend Polish (Priority 7)

### 9.1 Global Design Tokens

**File:** `frontend/src/index.css`

Ensure the following CSS variables are defined and consistent throughout the app. If they're missing or inconsistent, replace with:

```css
:root {
  /* Brand colors */
  --color-primary: #0f62fe;
  --color-primary-hover: #0353e9;
  --color-secondary: #6f6f6f;
  --color-accent: #08bdba;

  /* Semantic backgrounds */
  --color-bg-base: #0a0a0f;
  --color-bg-surface: #111118;
  --color-bg-card: #16161f;
  --color-bg-card-hover: #1e1e2a;

  /* Semantic text */
  --color-text-primary: #f4f4f4;
  --color-text-secondary: #a8a8b3;
  --color-text-muted: #6f6f7a;

  /* Status */
  --color-success: #24a148;
  --color-warning: #f1c21b;
  --color-danger: #da1e28;
  --color-bull: #24a148;
  --color-bear: #da1e28;

  /* Borders */
  --color-border: #282836;
  --color-border-subtle: #1e1e2a;

  /* Typography */
  --font-sans: "Inter", "SF Pro Display", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", monospace;

  /* Spacing */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  /* Shadows */
  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.4), 0 4px 16px rgba(0, 0, 0, 0.3);
  --shadow-elevated: 0 8px 32px rgba(0, 0, 0, 0.5);
}
```

### 9.2 ChatPage — Loading States

**File:** `frontend/src/ChatPage.tsx`

**Problems:**

- No skeleton/loading indicator while waiting for `/chat` response
- Messages render without animation — jarring appearance
- No error state when `/chat` returns error

**Fixes:**

1. Add a `TypingIndicator` component shown after user sends message:

```tsx
const TypingIndicator = () => (
  <div className="typing-indicator">
    <span />
    <span />
    <span />
  </div>
);
```

2. Message appearance animation — add CSS class `message-appear` with `animation: fadeSlideIn 0.2s ease-out` applied to each new message bubble.

3. Error state: if the API call fails, render an error message in the chat thread (not an alert):

```tsx
{
  error && (
    <div className="message assistant error">
      ⚠️ Something went wrong. Please try again or rephrase your question.
    </div>
  );
}
```

4. Auto-scroll to bottom on new message using `useEffect` + `scrollIntoView`.

5. Disable the send button and input while loading to prevent duplicate submissions.

### 9.3 DashboardPage — Refinements

**File:** `frontend/src/DashboardPage.tsx`

**Problems:**

- Quote search doesn't show a loading skeleton — it jumps
- Chart has no empty state
- AI insight cards are static — they don't update on symbol change

**Fixes:**

1. Add `QuoteCardSkeleton` component that renders a shimmering placeholder with the same dimensions as `QuoteCard`.

2. Chart empty state: show "Search for a symbol above to view the chart" with an icon when no data.

3. When user searches a symbol, re-fetch AI insights via `/invoke` with `multi_agent_analysis` for that ticker and update the insight cards.

4. Add a "Last updated" timestamp to the quote card so users know data freshness.

### 9.4 StructuredAnalysisMessage — Verdict Card

**File:** `frontend/src/StructuredAnalysisMessage.tsx`

**Problems:**

- Verdict badge does not use color coding
- Bull/bear cards not visually differentiated enough
- No confidence meter visual

**Fixes:**

1. Verdict badge color:

```tsx
const verdictColor =
  {
    "STRONG BUY": "#24a148",
    BUY: "#42be65",
    HOLD: "#f1c21b",
    SELL: "#ff832b",
    "STRONG SELL": "#da1e28",
    "INSUFFICIENT DATA": "#6f6f6f",
  }[verdict] ?? "#6f6f6f";
```

2. Bull card: left border `--color-bull`, slight green tint on background.
   Bear card: left border `--color-bear`, slight red tint on background.

3. Confidence meter: a horizontal bar showing `composite_confidence` out of 100, colored by verdict direction.

4. Key drivers: render as two columns (bull drivers left, bear drivers right) with colored bullet icons (▲ green for bull, ▼ red for bear).

### 9.5 HomePage — Hero Refinements

**File:** `frontend/src/HomePage.tsx`

1. Add a live market ticker strip at the top of the hero — shows 5-6 major indices/tickers scrolling horizontally. This data is fetched from `/invoke` quote.latest on mount for MSFT, AAPL, NVDA, AMZN, GOOGL, TSLA.

2. The feature rail cards should have subtle animated border glow on hover using CSS `box-shadow` animation.

3. Add a "Powered by real-time market data" badge row under the CTA buttons with small logos/icons for the data sources (generic icon — no third-party brand logos due to licensing).

### 9.6 Global — Error Boundaries

**File:** Create `frontend/src/ErrorBoundary.tsx`

```tsx
import { Component, ErrorInfo, ReactNode } from "react";

class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI Error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2>Something went wrong</h2>
          <p>Please refresh the page. If this persists, contact support.</p>
          <button onClick={() => this.setState({ hasError: false })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

Wrap all three page routes in `App.tsx` with `<ErrorBoundary>`.

### 9.7 Navigation — Active State & Mobile

**File:** `frontend/src/App.tsx` (or nav component)

1. Active route link must have a visible active state (underline or background highlight).
2. On mobile (< 768px), the nav should collapse into a hamburger menu.
3. The QuantVex logo/wordmark must be present in the top-left on all pages.

---

## 10. Fix Specification — INR Currency Consistency (Priority 8)

### 10.1 Problem

INR conversion is applied in three places with inconsistent logic:

- `mcp_server/finance_formatter.py` — hardcoded constant (e.g., `USD_TO_INR = 83.5`)
- `frontend/src/components/QuoteCard.tsx` — another hardcoded constant
- `frontend/src/DashboardPage.tsx` — fetches live FX rate from a public API

This means the same stock price can display as three different INR values depending on which component renders it.

### 10.2 Fix — Single source of truth

**Backend approach (recommended):**

1. In `mcp_server/config.py`, add:

```python
usd_inr_rate: Optional[float] = Field(None, env="USD_INR_RATE")  # Override for testing
```

2. In `finance_formatter.py`, replace the hardcoded constant with a function that fetches live rate (with 1-hour cache in Redis):

```python
async def get_usd_inr_rate() -> float:
    cached = await redis_client.get("fx:USD_INR")
    if cached:
        return float(cached)
    # Fetch from Alpha Vantage FX endpoint or Finnhub
    rate = await fetch_fx_rate("USD", "INR")
    await redis_client.set("fx:USD_INR", str(rate), ex=3600)
    return rate
```

3. The quote API response must include `inr_price` as a computed field so the frontend never needs to do its own FX conversion.

4. In `QuoteCard.tsx` and `DashboardPage.tsx`: remove all local FX conversion logic. Use `inr_price` from the API response directly. If `inr_price` is absent, show the USD price with a "₹ N/A" placeholder.

---

## 11. Fix Specification — Miscellaneous Bugs & Cleanup (Priority 9)

### 11.1 Layer Coupling — Reasoning Agents

**Files:** `finance_mcp/reasoning/bull_agent.py`, `finance_mcp/reasoning/bear_agent.py`

**Problem:** Both agents import handlers directly from `mcp_server/invoke_handlers`, coupling the domain layer to the server layer.

**Fix:** Extract the shared business logic from `handle_quote_latest`, `handle_trace_impact`, and `handle_news_analysis` into standalone service functions in `finance_mcp/services/`:

```
finance_mcp/services/
  quote_service.py       — get_quote(symbol) → QuoteResult
  graph_service.py       — trace_impact(target_vid, hops) → TraceResult
  news_service.py        — run_news_pipeline(query, ticker) → PipelineResult
```

Both the MCP server invoke handlers and the reasoning agents import from `finance_mcp/services`. The invoke handlers become thin wrappers. This eliminates the coupling.

### 11.2 Docstring fix

**File:** `scripts/seed_production_data.py`

Fix any docstring or comment that references `tests/` as the location of this script. The correct path is `scripts/seed_production_data.py`.

### 11.3 `capabilities.json` — sync with actual tools

Verify that `capabilities.json` lists exactly these tools with accurate schemas:

- `quote.latest`
- `quote.stream`
- `trace_impact`
- `analyze_news_impact`
- `multi_agent_analysis`

Remove any stale tool entries. Add a `version` field to the capabilities JSON: `"version": "1.0.0"`.

### 11.4 `validation.py` — extend symbol validation

Add validation for the new commodity VIDs introduced in the expanded graph (CRUDE_OIL, LITHIUM, RARE_EARTH, etc.) so that `trace_impact` calls with commodity VIDs are not rejected as invalid symbols.

```python
VALID_COMMODITY_VIDS = {
    "CRUDE_OIL", "NATURAL_GAS", "COAL", "SEMICONDUCTOR_WAFER",
    "LITHIUM", "COBALT", "COPPER", "RARE_EARTH", "ALUMINUM", "STEEL",
    "CORN", "WHEAT", "SOYBEANS", "COFFEE", "SUGAR", "PALM_OIL",
    "SHIPPING_CONTAINERS", "SEMICONDUCTOR_CHIPS", "SILICON", "NEON_GAS"
}

def validate_symbol_or_vid(value: str) -> str:
    if re.match(r'^[A-Z]{1,5}$', value):
        return value  # Stock ticker
    if value in VALID_COMMODITY_VIDS:
        return value  # Commodity VID
    raise ValueError(f"Invalid symbol or VID: {value}")
```

### 11.5 `news_analysis.py` — commodity anchor expansion

When `ticker_anchor` is a commodity VID (in `VALID_COMMODITY_VIDS`), the handler must skip the `find_companies_requiring` call and directly call `trace_impact` with the commodity VID. Currently the fallback logic may not handle this cleanly.

### 11.6 `/subscribe` and `/unsubscribe` — response consistency

Both endpoints must return a consistent JSON schema:

```json
{
  "success": true,
  "channel": "trade.AAPL",
  "message": "Subscribed successfully"
}
```

Currently the response format may differ between the two endpoints.

---

## 12. Verification Checklist

After all fixes are implemented, the following verification suite must pass. Run in order.

### 12.1 Unit Tests — must all pass

```bash
cd tests
pytest test_connectors.py -v
pytest test_graph_client.py -v
pytest test_queries.py -v
pytest test_insert.py -v
pytest test_event_parser.py -v
pytest test_event_ingestor.py -v
pytest test_pipeline.py -v
pytest test_multi_agent_analysis.py -v
pytest test_mcp_invoke.py -v
pytest test_trace_impact.py -v
```

**Expected:** 0 failures, 0 errors.

### 12.2 Graph Seeding Verification

```bash
python scripts/seed_production_data.py --dry-run
# Expected: prints company count >= 50, commodity count >= 20, edge counts printed

python scripts/seed_production_data.py
# Expected: all vertices and edges inserted with no errors

python scripts/verify_system.py
# Expected: all checks pass, graph connectivity verified
```

Manually verify these traces return non-empty results:

```
trace_impact(target_vid="TSMC", hops=3) → must return AAPL, NVDA, AMD, QCOM, MSFT, META, GOOGL
trace_impact(target_vid="CRUDE_OIL", hops=2) → must return XOM, CVX, COP, TSLA (via supply chain)
trace_impact(target_vid="RARE_EARTH", hops=2) → must return TSLA, GE, RTX, LMT, NVDA
```

### 12.3 Chat Agent — Domain Guardrail Tests

Send the following messages to `/chat` and verify responses:

| Input                                             | Expected behavior                                        |
| ------------------------------------------------- | -------------------------------------------------------- |
| "What is football?"                               | Domain refusal message, no tool call                     |
| "Who won the World Cup?"                          | Domain refusal message, no tool call                     |
| "What is the price of AAPL?"                      | Calls `get_stock_quote`, returns real quote              |
| "What is happening with TSMC and Taiwan?"         | Calls `analyze_news_impact`, returns live news           |
| "Give me a full analysis of NVDA"                 | Calls `multi_agent_analysis`, returns structured verdict |
| "Which companies are exposed to a TSMC shutdown?" | Calls `trace_supply_chain_impact`                        |
| "Tell me about the oil market disruption"         | Calls `analyze_news_impact` with oil-related query       |
| Follow-up: "How does that affect TSLA?"           | Uses conversation history, calls relevant tool           |

### 12.4 Judge Agent — Verdict Quality Tests

Run `multi_agent_analysis` for the following tickers and verify:

| Ticker                          | Expected verdict type                             |
| ------------------------------- | ------------------------------------------------- |
| NVDA                            | STRONG BUY or BUY (high bull confidence expected) |
| Any ticker with bad recent news | SELL or STRONG SELL                               |

Verify that verdict is NEVER empty and conviction is NEVER blank.
Verify that `key_drivers` contains exactly 3 bull and 3 bear items.

### 12.5 Health Endpoint

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "components": {
    "redis": { "status": "ok" },
    "nebula_graph": { "status": "ok" },
    "qdrant": { "status": "ok" },
    "neo4j": { "status": "ok" },
    "openai": { "status": "ok" },
    "subscriptions": { "status": "ok", "count": 0 }
  }
}
```

If any component is down, `status` must be `"degraded"` and HTTP status must be 503.

### 12.6 Security Checks

1. Make a request to `/chat` with a wrong API key → must receive 401.
2. Make 65 requests in 60 seconds with the same API key → request 61 must receive 429.
3. Check browser network tab — `X-API-Key` header value must come from `VITE_API_KEY` env var, not a hardcoded string.
4. Check CORS headers — `Access-Control-Allow-Origin` must not be `*` in production config.

### 12.7 Frontend Smoke Tests

Manually navigate through:

1. **HomePage** — hero loads, market ticker strip shows live data, feature rail animates on hover, CTA buttons navigate correctly.
2. **ChatPage** — type a finance question, verify typing indicator appears, response loads, structured cards render for multi-agent queries.
3. **ChatPage** — type "what is football", verify domain refusal message.
4. **DashboardPage** — search AAPL, verify quote card shows with INR price matching the backend `inr_price` field, chart renders, AI insight cards update.
5. **ErrorBoundary** — manually trigger a rendering error to confirm the error boundary catches it.
6. **Mobile** — resize browser to 375px width, verify nav collapses to hamburger, all pages are scrollable.

### 12.8 INR Consistency Check

1. Search AAPL in Dashboard — note the INR price.
2. Ask "What is the price of AAPL?" in Chat — note the INR price in the response.
3. Both must display the same INR value (within ±1% tolerance for market movement during the test).

### 12.9 Async / Event Loop

Load test: use `locust` or `ab` to send 20 concurrent `/invoke` requests:

```bash
ab -n 100 -c 20 -H "X-API-Key: test" -T "application/json" \
  -p /tmp/payload.json http://localhost:8000/invoke
```

Verify: response times are consistent. No request should take longer than 15 seconds. No 500 errors.

---

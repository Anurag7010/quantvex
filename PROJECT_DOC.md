# PROJECT MASTER DOCUMENT

## QuantVex: AI-Powered Financial Intelligence Platform

**Version:** 2.0.0 | **License:** MIT | **Primary Language:** Python 3.11 | **Repository:** https://github.com/Anurag7010/finance-mcp

---

## Table of Contents

1. [Project Identity](#1-project-identity)
2. [Problem Statement & Motivation](#2-problem-statement--motivation)
3. [System Overview](#3-system-overview)
4. [Core Subsystems](#4-core-subsystems)
5. [Technology Stack](#5-technology-stack)
6. [MCP Tool Catalog](#6-mcp-tool-catalog)
7. [API Surface](#7-api-surface)
8. [Supply Chain Graph — Deep Dive](#8-supply-chain-graph--deep-dive)
9. [Multi-Agent Reasoning — Deep Dive](#9-multi-agent-reasoning--deep-dive)
10. [Quantitative Summary](#10-quantitative-summary)
11. [Security Model](#11-security-model)
12. [Operational Characteristics](#12-operational-characteristics)
13. [Limitations & Future Work](#13-limitations--future-work)
14. [Glossary](#14-glossary)
15. [References & Attribution](#15-references--attribution)

---

## 1. Project Identity

**Full Name:** QuantVex  
**Tagline:** AI-Powered Financial Intelligence Platform  
**Version:** 2.0.0 (phase-1 complete)

### Abstract

QuantVex is a full-stack financial intelligence system that grounds every AI-generated market analysis in live, verifiable tool-call data. The platform exposes a Model Context Protocol (MCP) server — built on FastAPI and backed by OpenAI GPT-4o — that integrates real-time market data connectors, a Memgraph supply chain knowledge graph, SEC EDGAR filing extraction, a live news ingestion pipeline, and an adversarial multi-agent investment reasoning engine. When a user poses a financial question, GPT-4o deterministically routes the query through one or more of six specialised MCP tools before formulating a response, ensuring that claims about current prices, supply chain dependencies, SEC-disclosed supplier relationships, and market-moving news are derived from live data rather than from the model's training-time knowledge. The system further supports real-time Server-Sent Events (SSE) streaming of the adversarial debate transcript, and persists every investment verdict to a SQLite store for longitudinal accuracy tracking. The frontend is a React 19 / TypeScript application rendering structured analysis as visual cards. QuantVex addresses the reliability gap that exists when general-purpose LLMs are applied directly to finance: every factual claim is auditable, every data source is cited, and every verdict is accuracy-checked against future price movement.

---

## 2. Problem Statement & Motivation

### The Gap in Existing Financial Tools

Existing financial tooling falls into two categories that both leave significant gaps. Traditional data dashboards (Bloomberg Terminal, Yahoo Finance) provide real-time data but offer no synthesis, forcing the analyst to construct the causal chain manually. Conversational AI assistants (ChatGPT, Gemini) can synthesise and explain, but their responses are grounded only in training data — they cannot retrieve a live price, traverse a supply chain graph, or read yesterday's SEC filing. The intersection — an AI that synthesises live, verifiable data — has not been productised for professional-grade financial analysis.

### Why Grounded AI Is Preferable for Finance

A purely generative LLM response to a finance query carries three structural risks. First, **temporal staleness**: the model's knowledge cutoff may predate the market event in question by months or years. Second, **hallucination risk**: the model may generate plausible-sounding but incorrect price levels, earnings figures, or supplier relationships. Third, **unauditability**: the analyst cannot verify which data source produced a given claim. QuantVex addresses all three by making tool-call execution mandatory for any data-dependent claim. The system prompt enforces domain guardrails that require the model to call `get_stock_quote` before citing a price, `analyze_news_impact` before commenting on a recent event, and `trace_supply_chain_impact` before making supply chain assertions. Tool failure is handled gracefully — the model falls back to training knowledge with an explicit disclaimer — but the primary path is always live data.

### Limitations of Existing Approaches

Static dashboards fail on synthesis: a supply chain analyst must manually correlate a geopolitical event with the set of downstream companies, then manually look up each company's exposure. Multi-agent financial platforms exist (e.g., FinGPT, BloombergGPT) but are primarily focused on fine-tuned language models rather than on the real-time tool-call architecture that grounds responses in live data. RAG-based financial systems retrieve from static document stores rather than live graph traversals and live APIs. QuantVex combines all three missing capabilities — live data retrieval, graph-based causal reasoning, and adversarial multi-agent synthesis — into a single unified system.

---

## 3. System Overview

### High-Level Architecture

QuantVex is organised into five tiers: a React frontend, a FastAPI MCP server, a set of specialised domain engines, a cache layer, and an infrastructure tier comprising Memgraph, Redis, and Qdrant.

The **frontend tier** is a React 19 / TypeScript single-page application that communicates with the backend exclusively over HTTPS with an `X-API-Key` header. It renders structured analysis as component cards (VerdictCard, BullCaseCard, BearCaseCard, MarketDataCard) and supports a real-time streaming view via the EventSource API connected to the SSE endpoint.

The **FastAPI MCP server** (`mcp_server/server.py`) is the system's entry point and enforcement boundary. It implements all fourteen HTTP endpoints, enforces API key authentication, applies a **60-request-per-60-second** in-memory rate limit using a per-key deque, and routes incoming requests to the appropriate handler. The server also hosts a GPT-4o chat agent (`mcp_server/chat_agent.py`) that maintains a **20-turn** rolling conversation history and enforces domain guardrails through a structured system prompt and a pre-LLM keyword filter.

The **domain engines** are divided into six subsystems: (1) market data connectors (`connectors/`), (2) supply chain graph client (`src/finance_mcp/graph/`), (3) causal beta calibrator (`src/finance_mcp/causal/`), (4) SEC EDGAR integration (`src/finance_mcp/edgar/`), (5) news ingestion and event propagation pipeline (`src/finance_mcp/news/` + `ingestion/`), and (6) multi-agent investment reasoning (`src/finance_mcp/reasoning/`).

The **cache tier** implements a two-level waterfall: Qdrant semantic cache (similarity threshold **0.86**, recency window **5 minutes**) for near-duplicate query deduplication, and Redis 7 for hot quote snapshots. Market indices are cached in Redis for **300 seconds**; crypto quotes for **30 seconds**.

The **infrastructure tier** comprises three containerised services managed by Docker Compose: Memgraph (graph database, Bolt port 7687), Redis 7 (snapshot cache), and Qdrant (vector database, HTTP port 6333).

### Data Flow

The end-to-end data flow for a typical investment analysis query proceeds as follows:

1. The user submits a message via the React chat interface. The frontend sends a `POST /chat` request with an `X-API-Key` header.
2. The FastAPI server validates the API key and checks the rate limit bucket for that key.
3. The `QuantVexChatAgent.chat()` method prepends the system prompt and the last 20 conversation turns, then calls the OpenAI Chat Completions API with `tool_choice="auto"` and **temperature 0.1**.
4. GPT-4o evaluates the query against the tool routing rules in the system prompt and returns one or more tool calls (e.g., `trace_supply_chain_impact` + `analyze_news_impact`).
5. The server executes each tool call sequentially via `_execute_tool()`, which dispatches to the appropriate MCP invoke handler.
6. Each handler checks the Qdrant semantic cache; on a miss, it calls the Memgraph graph client, live market APIs, or the NewsData.io adapter as appropriate.
7. Tool results are appended to the conversation as `role: tool` messages and a second LLM call is made with `temperature 0.1` and `max_tokens 4096` to produce the final prose response.
8. The response is returned to the frontend, which parses embedded structured JSON and renders the appropriate card components.

For SSE streaming queries (`GET /stream/analysis`), step 7 is replaced by an async generator that yields Server-Sent Events at each reasoning milestone — bull thesis completion, bear attack, rebuttal, judge verdict — before emitting the final `done` event.

### Key Design Decisions

**MCP as the tool protocol** was chosen because it provides a standardised schema-validated interface between the LLM and the tool execution layer, enabling deterministic routing without prompt engineering fragility.

**Memgraph** (Bolt/Cypher, neo4j Python driver) was chosen over a relational database for the supply chain graph because graph traversal at variable depth (`max_hops` 1–5) is natively expressed in Cypher and executes in a single query, whereas SQL would require recursive CTEs with poor latency characteristics.

**Adversarial debate architecture** was chosen over a single-agent approach because investment analysis is inherently a two-sided argument. The bull-bear-judge pipeline forces the system to surface and challenge the weakest claim in its own upside thesis, producing more robust recommendations.

**SQLite for verdict history** was chosen over a full database because verdict volume is modest (one per analysis request), the schema is fixed, and the 5-day/30-day accuracy check writes happen asynchronously in background tasks — there is no need for the concurrency guarantees of a production database.

---

## 4. Core Subsystems

### 4.1 Real-Time Market Data Layer

**Purpose:** Retrieve current prices for equity and cryptocurrency instruments, normalised to a unified `QuoteData` schema with INR conversion.

**Internal operation:** Quote requests follow a four-level cache waterfall. First, the Qdrant semantic cache is queried with the request text; any response with cosine similarity ≥ **0.86** within the last **5 minutes** is returned immediately. On a semantic cache miss, the Redis snapshot store is checked for a cached `QuoteData` object keyed by `snapshot:{SYMBOL}`. On a Redis miss, the Finnhub REST API is queried (primary provider, **60 calls/minute** limit enforced by a **1.0-second** minimum inter-request interval). On Finnhub failure or a non-US symbol, Alpha Vantage REST is tried (**5 calls/minute** limit, **12-second** minimum interval). All connectors implement exponential backoff retry with `tenacity` (**3 attempts**, backoff multiplier 1, min 2s, max 30s).

Indian market indices (NIFTY 50, SENSEX) and the USD/INR rate are fetched server-side via Yahoo Finance's undocumented v8 chart API and Open Exchange Rates respectively, bypassing browser CORS constraints. The USD/INR rate is used to compute `inr_price` on all quote responses. Market indices are cached in Redis for **300 seconds**; crypto quotes for **30 seconds**.

For cryptocurrency, Binance REST (`/api/v3/ticker/24hr`) is queried directly with a **7 supported symbols** whitelist: BTC, ETH, BNB, SOL, XRP, ADA, DOGE. Real-time Binance WebSocket streams are also available via the `quote.stream` MCP tool for continuous tick ingestion.

**Key design choices:** The fallback chain prioritises data availability over consistency. Finnhub provides millisecond-latency global equity quotes; Alpha Vantage covers a broader universe with longer latency. The Qdrant semantic layer allows near-duplicate queries (e.g., "price of Apple" vs "Apple stock price") to share a single cached response, reducing API call volume.

### 4.2 Supply Chain Knowledge Graph

**Purpose:** Model company-to-company and company-to-commodity dependency relationships as a graph, enabling multi-hop traversal to compute the blast radius of any supply disruption.

**Internal operation:** The graph resides in Memgraph and is accessed through `GraphClient` (`src/finance_mcp/graph/client.py`), a connection-pooled Bolt client using the official neo4j Python driver. All queries use parameterised Cypher; user-supplied vertex IDs are validated against `^[A-Za-z0-9_.\-]{1,64}$` before being passed as query parameters. The sole use of an f-string in query construction is for the `max_hops` integer embedded in the multi-hop traversal query, which is validated as a Python `int` in `[1, 5]` before interpolation — a bounded integer literal cannot carry Cypher injection.

The base graph (seeded by `scripts/seed_production_data.py`) contains **57 Company** vertices, **20 Commodity** vertices, **64 DEPENDS_ON** edges, **53 REQUIRES** edges, and **39 IMPACTS** edges across **8 pre-seeded historical events**. The seed script is idempotent (uses Cypher `MERGE` semantics) and supports `--dry-run`.

Multi-hop traversal uses a variable-depth Cypher pattern. For a TSMC disruption at `max_hops=2`, the query returns all companies reachable within two DEPENDS_ON hops from TSMC: AAPL (weight 0.95), NVDA (0.98), AMD (0.95), QCOM (0.90), and then their dependents MSFT, META, AMZN, GOOGL, TSLA, and others.

**Key design choices:** Dependency weights in `[0.0, 1.0]` encode exposure severity. After causal calibration (§4.3), each edge additionally stores `beta`, `lag_days`, and `r_squared`, transforming the weight-only graph into a quantitative causal model.

### 4.3 Causal Beta Calibration

**Purpose:** Quantify, for each DEPENDS_ON edge, the magnitude and timing of price shock transmission from an upstream supplier to a downstream dependent.

**Internal operation:** The calibration pipeline (`src/finance_mcp/causal/`) operates as follows. The `calibrate_all_edges()` function fetches every DEPENDS_ON edge from Memgraph, then downloads **2 years** of daily close prices for each unique ticker via yfinance (`fetch_price_history()`). For each edge `(downstream) -[:DEPENDS_ON]-> (upstream)`, `compute_edge_beta()` fits an OLS regression at each lag `l ∈ [1, 30]` trading days:

```
downstream_return(t) ~ upstream_return(t - l)
```

where returns are computed as log-returns. The lag that maximises R² is selected as `lag_days`. A Granger causality F-test is then run at that lag to produce `p_value`. The resulting `EdgeCalibration` dataclass holds `beta`, `lag_days`, `r_squared`, `p_value`, and `n_observations`. The minimum required common observation count is `max_lag + 30 = 60` trading days; edges with insufficient data are skipped.

After calibration, three fields are written back to each DEPENDS_ON edge in Memgraph: `beta` (OLS slope), `lag_days` (optimal lag in trading days), and `r_squared` (coefficient of determination). These fields appear in the `trace_impact` tool's output schema and are returned to the LLM for quantitative supply chain reasoning.

**Key design choices:** OLS with lag search over **30 trading days** was chosen over more complex time-series models (VAR, ARIMA) for interpretability and reproducibility. The Granger causality test provides a statistical guard against spurious correlations. Calibration runs as a background task (`/calibrate/edges`) to avoid blocking the request path.

### 4.4 SEC EDGAR Integration

**Purpose:** Automatically extract real-world supplier and customer relationships from 10-K filings and write them to the supply chain graph as `DEPENDS_ON` edges, keeping the graph current with actual disclosed data.

**Internal operation:** The `edgar_refresh` pipeline (`src/finance_mcp/edgar/`) proceeds in five steps:

1. **Ticker validation:** The ticker is checked against `^[A-Za-z0-9_.\-]{1,64}$`. Non-US tickers (TSMC, Samsung, ASML) that are absent from the SEC registry return a clear error.
2. **CIK resolution:** `get_cik()` resolves the ticker to a zero-padded 10-digit CIK by querying the EDGAR company tickers JSON (`/files/company_tickers.json`). Results are cached in a module-level `_CIK_CACHE` dict to avoid re-downloading the ~600 KB file.
3. **10-K fetch:** `fetch_10k_filing()` retrieves the most recent 10-K filing's Business and Risk Factors sections (combined ≤ **24,000 characters**, **12,000 per section**) via EDGAR's XBRL submissions API. The `_MIN_DELAY = 0.12s` inter-request pause respects EDGAR's 10 req/sec fair-access policy.
4. **GPT-4o extraction:** `extract_supplier_relationships()` sends the truncated filing text to GPT-4o with `temperature=0.0` and `response_format={"type": "json_object"}`. The structured output lists each named supplier or customer with fields: `supplier_ticker`, `supplier_name`, `relationship_type`, `dependency_strength` (0.0–1.0), and `evidence_quote` (verbatim, ≤120 chars).
5. **Graph write-back:** `update_graph_from_filing()` calls `GraphClient.insert_company()` for any newly discovered company and `insert_depends_on()` for each relationship, tagging edges with `source='EDGAR'` and `filing_date`.

**Key design choices:** EDGAR URLs are constructed from structured CIK and accession number fields, never from user input, eliminating SSRF surface. GPT-4o output is fully JSON-parsed and field-validated (type checks, length caps, self-reference exclusion) before any graph write occurs.

### 4.5 Live News Ingestion & Event Propagation

**Purpose:** Fetch real-time news, identify supply-disruption events, write them to the graph as Event vertices with IMPACTS edges, and compute the downstream company cascade.

**Internal operation:** The pipeline (`src/finance_mcp/news/` + `src/finance_mcp/ingestion/`) operates as follows. The `NewsClient` queries NewsData.io with a keyword search (up to **20 articles**, configurable). Each article is passed to `EventParser.parse_articles()`, a pure-Python rule-based classifier that scans the headline and description for disruption keywords and maps them to severity scores (`medium=5`, `high=8`, `critical=10`). Recognised entities (company tickers and commodity IDs) are extracted from the text to populate the `impacted_entities` list of each `ParsedEvent`.

The `EventIngestor` then writes each event to Memgraph: one `Event` vertex and one `IMPACTS` edge per impacted entity, recording `event_id`, `description`, `severity`, and `impact_time`. After ingestion, `handle_news_analysis()` calls `GraphClient.trace_impact()` for each impacted company to compute the full downstream cascade — the set of companies reachable from each affected node within `max_hops` DEPENDS_ON hops.

**Key design choices:** Rule-based event parsing was chosen for determinism and zero API cost. The parser is intentionally conservative — false negatives (missed events) are preferable to false positives (spurious graph writes). The pipeline is designed for future replacement of the rule-based parser with an LLM extraction step without changing the `ParsedEvent` contract.

### 4.6 Multi-Agent Investment Reasoning

**Purpose:** Produce structured, adversarially-validated investment verdicts by running a bull agent and bear agent in sequence, forcing a targeted rebuttal, and synthesising the debate through a deterministic judge.

**Internal operation:** The orchestrator (`src/finance_mcp/reasoning/orchestrator.py`) runs a four-step sequential adversarial debate:

**Step 1 — Bull Agent** (`run_bull_agent`): Calls `get_quote()` (if ticker provided), `trace_impact()` (hops=2), and `analyze_news_impact()` (if query contains disruption keywords). Each successful tool call adds signals and increments confidence: +0.12 for a live quote, +0.12 for graph dependents found, +0.08 for news events, +0.06 for cascade companies. Base confidence is **0.35**. The agent also identifies the `weakest_claim` — the most contestable signal — for the bear agent to target.

**Step 2 — Bear Agent** (`run_bear_agent`): Receives the bull's `weakest_claim` as `attack_target`. The bear calls `trace_impact()` with `hops=3` (wider blast radius) and `analyze_news_impact()`. Confidence starts at **0.40**; +0.08 for targeting a specific claim, +0.15 for graph dependents found, +0.08 for news events. The attack target is stored in the bear's `metadata` for the judge's use.

**Step 3 — Bull Rebuttal** (`_generate_rebuttal`): A deterministic rule-based rebuttal. If `bull_confidence ≥ bear_confidence × 0.85`, the bull maintains its thesis; otherwise it concedes the targeted claim while defending the remaining signals. No LLM call is made for this step.

**Step 4 — Judge Agent** (`run_judge_agent`): A fully deterministic (no LLM) function that computes the verdict from the confidence scores and their gap. See §9 for the exact verdict mapping.

The SSE streaming variant (`run_streaming_analysis`) runs the same four steps but yields SSE events at each milestone, allowing the frontend to render progress in real time.

**Key design choices:** Sequential execution (bull → bear → rebuttal → judge) rather than concurrent was chosen because the bear must see the bull's thesis to target it. The judge is entirely deterministic — no LLM is involved — ensuring reproducible verdicts for the same confidence inputs.

### 4.7 Verdict History & Accuracy Tracking

**Purpose:** Persist every investment verdict to a SQLite store and automatically measure its directional accuracy against future price movements.

**Internal operation:** `record_verdict()` (`src/finance_mcp/verdict_history/tracker.py`) writes a row to the `verdicts` table and spawns a background `asyncio.Task` (`_schedule_price_updates`) that sleeps for **5 trading days** (`5 × 86,400 seconds`), fetches the current price via yfinance, records `price_5d` and `correct_5d`, then sleeps an additional **25 trading days** and repeats for the 30-day window. `correct_5d` is 1 if the price moved in the predicted direction by more than **2%** (BUY/STRONG BUY: upward; SELL/STRONG SELL: downward), 0 otherwise. HOLD and INSUFFICIENT DATA verdicts are excluded from accuracy measurement.

The `compute_accuracy_stats()` function aggregates the `verdicts` table by verdict type, computing per-window accuracy percentages from resolved rows only. This is exposed via `GET /verdicts/accuracy`.

The SQLite schema (`verdicts` table) contains **11 fields**: `id` (UUID4), `ticker`, `query`, `verdict`, `confidence`, `created_at`, `price_at_verdict`, `price_5d`, `price_30d`, `correct_5d`, `correct_30d`.

**Key design choices:** SQLite was chosen for simplicity — verdict volume is bounded by the rate limit (**60/minute**), and the accuracy check writes are infrequent asynchronous background events. The 2% threshold for correctness is an explicit design choice that treats very small moves as noise rather than signal.

### 4.8 Cache Architecture

**Purpose:** Minimise external API calls and latency for repeated or semantically similar queries.

**Internal operation:** The cache implements a two-level waterfall. The **Qdrant semantic cache** (`SemanticCacheClient`) uses the `all-MiniLM-L6-v2` sentence transformer model (vector size **384**) to embed query text and performs a cosine similarity search against cached responses. A response is served from cache only if similarity ≥ **0.86** (configurable via `semantic_cache_threshold`) and the cached entry was created within the last **5 minutes** (configurable via `semantic_cache_recency_minutes`). Cache writes store `agent_id`, `symbol`, `query_text`, `response_text`, and a Unix timestamp in the Qdrant payload.

The **Redis snapshot cache** stores serialised `QuoteData` objects keyed by `snapshot:{SYMBOL}` as Redis hashes. The `get_snapshot()` method retrieves and deserialises cached quotes without any TTL check — TTL management is handled by the caller's `max_age_sec` parameter. Market indices and crypto quotes are stored with explicit `ex=300` and `ex=30` TTL arguments respectively.

**Key design choices:** The Qdrant semantic layer handles the common case where users phrase the same question differently. The Redis layer handles the high-frequency case of multiple agents querying the same symbol within a short window.

### 4.9 AI Chat Interface

**Purpose:** Provide a conversational interface backed by GPT-4o with strict finance-domain guardrails, deterministic tool routing, and graceful degradation when tools are unavailable.

**Internal operation:** The `QuantVexChatAgent` (`mcp_server/chat_agent.py`) maintains a rolling `conversation_history` list capped at **20 turns**. On each `chat()` call, it prepends the system prompt and the last 20 turns to the messages array. A pre-LLM keyword filter (`_is_clearly_out_of_scope`) checks for out-of-scope terms (e.g., "football", "recipe", "coding") and for absence of any finance terms from a 80-term whitelist; queries that fail this check receive a canned refusal without an LLM call.

The system prompt enforces six mandatory tool-routing rules: company/ticker mentioned → `trace_supply_chain_impact`; news/current events → `analyze_news_impact`; current price → `get_stock_quote`; investment thesis → `multi_agent_analysis`; EDGAR/10-K → `edgar_refresh`; combinations are explicitly specified. Tool failures are suppressed from the user-facing response: the agent prompt instructs the model to never open with an apology for a tool failure and to always produce a complete answer from training knowledge if all tools fail.

The agent exposes **5 GPT-4o function declarations** (the `quote.stream` tool is not exposed to the chat agent as it is a subscription mechanism rather than a query tool).

---

## 5. Technology Stack

| Layer | Technology | Version | Role | Why Chosen |
|---|---|---|---|---|
| AI Model | OpenAI GPT-4o | Latest | Function calling, EDGAR extraction, chat | Best-in-class function calling reliability; structured JSON output mode |
| Backend Framework | FastAPI | 0.104 | HTTP server, routing, validation | Async-native, Pydantic integration, OpenAPI docs out of box |
| Runtime | Python | 3.11 | Entire backend | AsyncIO maturity, ecosystem breadth, type hints |
| Graph Database | Memgraph | Latest | Supply chain knowledge graph | Bolt/Cypher compatible, faster than Neo4j for in-memory workloads |
| Graph Driver | neo4j Python driver | 5.x | Bolt client | Official driver with connection pooling, parameterised queries |
| Semantic Cache | Qdrant | Latest | Cosine similarity search | Native vector store with filtering, simple Python SDK |
| Embedding Model | sentence-transformers all-MiniLM-L6-v2 | — | Query embedding | 384-dim, fast inference, strong semantic similarity |
| Hot Cache | Redis | 7 | Quote snapshots, index cache | Sub-millisecond reads, TTL support, wide ecosystem |
| Market Data (primary) | Finnhub REST | v1 | Real-time equity quotes | 60 req/min free tier, global coverage |
| Market Data (fallback) | Alpha Vantage REST | — | Equity quotes, intraday | Broader symbol universe as fallback |
| Crypto Data | Binance WebSocket & REST | v3 | Crypto prices, live streams | Zero-cost, high-reliability for major pairs |
| News | NewsData.io REST | — | Real-time news articles | Structured API, geolocation and category filters |
| SEC Filings | EDGAR REST | — | 10-K text extraction | Official SEC data, no API key required |
| Causal Calibration | yfinance + statsmodels | — | OLS regression, Granger test | yfinance: easiest programmatic access to historical OHLCV; statsmodels: full OLS + Granger |
| Verdict Storage | SQLite | 3 | Verdict history, accuracy tracking | Zero-infra, sufficient for bounded-rate writes |
| Frontend Framework | React | 19 | SPA with component cards | Concurrent features, modern hooks |
| Frontend Language | TypeScript | 4.9 | Type-safe API client, components | Compile-time correctness for API contract |
| Styling | Tailwind CSS | 3 | Utility-first styling | Rapid iteration, no CSS file management |
| Animation | Framer Motion | — | Page and card transitions | Declarative animation for React |
| Charts | Recharts | — | Price history visualisation | React-native, composable |
| Containerisation | Docker Compose | — | Service orchestration (dev) | Zero-config local stack |
| HTTP Client (backend) | httpx / aiohttp | — | External API calls | Async-native; aiohttp for streaming, httpx for REST |

---

## 6. MCP Tool Catalog

### 6.1 `quote.latest`

| Field | Value |
|---|---|
| **Input parameters** | `symbol` (string, required); `exchange` (string, optional); `maxAgeSec` (integer, default 60) |
| **Output fields** | `symbol`, `price`, `inr_price`, `usd_inr_rate`, `timestamp`, `data_source`, `cache_hit`, `latency_ms` |
| **Execution path** | Qdrant semantic cache → Redis snapshot → Finnhub REST → Alpha Vantage REST → normalise to `QuoteData` |
| **Typical latency** | <5ms (cache hit); 80–200ms (Finnhub); 200–400ms (Alpha Vantage) |
| **Agents using it** | Bull agent (confidence check), Bear agent (price context), Chat agent |

### 6.2 `quote.stream`

| Field | Value |
|---|---|
| **Input parameters** | `symbol` (string, required); `channel` (enum: trades/quotes, default: trades) |
| **Output fields** | `subscription_id`, `status`, `channel`, `message` |
| **Execution path** | `BinanceWebSocketConnector.connect()` → streams trade ticks; subscription ID returned for polling |
| **Typical latency** | <100ms to first tick after connection |
| **Agents using it** | Direct API calls only; not exposed to chat agent |

### 6.3 `trace_impact`

| Field | Value |
|---|---|
| **Input parameters** | `ticker` (string, required, max 64 chars, `^[A-Za-z0-9_.\-]+$`); `max_hops` (integer, 1–5, default 2) |
| **Output fields** | `ticker`, `max_hops`, `impacted_companies` (array with `ticker`, `name`, `sector`, `beta`, `lag_days`, `r_squared`), `impacted_count` |
| **Execution path** | VID validation → `GraphClient.trace_impact()` → variable-depth Cypher traversal → annotate with causal betas |
| **Typical latency** | 5–50ms (graph ping); 50–200ms (cold Memgraph traversal) |
| **Agents using it** | Bull agent (hops=2), Bear agent (hops=3), Chat agent |

### 6.4 `analyze_news_impact`

| Field | Value |
|---|---|
| **Input parameters** | `query` (string, required); `limit` (integer, 1–20, default 10); `max_hops` (integer, 1–5, default 2); `ticker` (string, optional anchor) |
| **Output fields** | `query`, `articles_fetched`, `events_found`, `events_ingested`, `news_events`, `directly_affected`, `downstream_cascade`, `total_cascade_companies` |
| **Execution path** | NewsData.io fetch → `EventParser.parse_articles()` → `EventIngestor.ingest()` → `GraphClient.trace_impact()` per entity |
| **Typical latency** | 500ms–2s (network + graph) |
| **Agents using it** | Bull agent (if query contains disruption keywords), Bear agent, Chat agent |

### 6.5 `multi_agent_analysis`

| Field | Value |
|---|---|
| **Input parameters** | `query` (string, required); `ticker` (string, optional) |
| **Output fields** | `query`, `ticker`, `bull_case`, `bear_case`, `final_verdict`, `verdict`, `conviction`, `confidence`, `composite_confidence`, `confidence_gap`, `summary`, `key_drivers`, `time_horizon`, `generated_at` |
| **Execution path** | Bull agent → Bear agent (targeted attack) → Bull rebuttal → Judge agent (deterministic) → SQLite verdict record |
| **Typical latency** | 3–10s (two LLM calls + graph + news) |
| **Agents using it** | Chat agent; direct API via `/invoke` |

### 6.6 `edgar_refresh`

| Field | Value |
|---|---|
| **Input parameters** | `ticker` (string, required; must be SEC-registered) |
| **Output fields** | `ticker`, `filing_date`, `relationships_found`, `new_edges_added`, `updated_edges`, `companies_discovered`, `errors` |
| **Execution path** | CIK resolution (cached) → EDGAR submissions API → 10-K text fetch → GPT-4o extraction (temp=0.0, JSON mode) → field validation → `GraphClient.insert_depends_on()` per relationship |
| **Typical latency** | 5–15s (EDGAR network + GPT-4o call) |
| **Agents using it** | Chat agent; direct API via `/invoke` |

---

## 7. API Surface

### Authentication Model

All endpoints except `GET /health` and `GET /.well-known/mcp` require the `X-API-Key` request header. The header value is compared against the `MCP_API_KEY` environment variable. Invalid or missing keys return HTTP 401.

### Rate Limiting

Each unique API key is allocated a sliding-window bucket (implemented as a `collections.deque` with `maxlen=60`). The window is **60 requests per 60 seconds**. Requests that exceed this limit return HTTP 429.

### Endpoint Table

| Method | Path | Auth | Request Body | Response Schema | Purpose |
|---|---|---|---|---|---|
| `GET` | `/.well-known/mcp` | None | — | MCP metadata JSON | MCP protocol discovery |
| `GET` | `/capabilities` | None | — | Full tool catalog JSON | Tool schema discovery |
| `POST` | `/invoke` | Required | `{tool_name, arguments, agent_id?, query_text?}` | `ToolResponse` | Execute any MCP tool |
| `POST` | `/chat` | Required | `{message}` | `{response, success, error?}` | GPT-4o conversational interface |
| `GET` | `/stream/analysis` | Query param `api_key` | — | SSE stream | Real-time multi-agent reasoning |
| `POST` | `/subscribe` | Required | `{symbol, channel, agent_id?}` | `ToolResponse` | Subscribe to price stream |
| `POST` | `/unsubscribe` | Required | `{subscription_id}` | `ToolResponse` | Cancel stream subscription |
| `GET` | `/subscriptions` | None | — | `{subscriptions: [...]}` | List active subscriptions |
| `POST` | `/calibrate/edges` | Required | — | `{status, message}` | Trigger background causal calibration |
| `GET` | `/verdicts/history` | Required | `?ticker=` (optional) | `{verdicts: [...]}` | Verdict history (last 100) |
| `GET` | `/verdicts/accuracy` | Required | — | Per-verdict accuracy stats | Accuracy by verdict type |
| `GET` | `/market/indices` | None | — | NIFTY/SENSEX/USD-INR JSON | Live Indian market indices |
| `GET` | `/market/crypto/{symbol}` | None | — | Crypto quote JSON | Live crypto via Binance |
| `GET` | `/health` | None | — | Deep health check JSON | Service liveness |

**Note:** The `/stream/analysis` endpoint accepts `api_key` as a query parameter rather than a header because the browser `EventSource` API does not support custom headers on SSE connections. The key is validated server-side on every request.

---

## 8. Supply Chain Graph — Deep Dive

### Vertex Schema

```cypher
// Company vertex
MERGE (c:Company {ticker: $ticker})
SET c.name = $name, c.sector = $sector

// Commodity vertex
MERGE (c:Commodity {commodity_id: $commodity_id})
SET c.name = $name, c.category = $category

// Event vertex
MERGE (e:Event {event_id: $event_id})
SET e.description = $description, e.severity = $severity
```

| Vertex Type | Properties | Notes |
|---|---|---|
| `Company` | `ticker` (PK), `name`, `sector` | Ticker is the vertex identifier; sector from S&P classification |
| `Commodity` | `commodity_id` (PK), `name`, `category` | Categories: Energy, Metals & Mining, Electronics, Agriculture, Logistics |
| `Event` | `event_id` (PK), `description`, `severity` | Severity integer: medium=5, high=8, critical=10 |

### Edge Schema

| Edge Type | Source | Target | Properties | Notes |
|---|---|---|---|---|
| `DEPENDS_ON` | Company | Company | `weight` (0.0–1.0), `beta` (float), `lag_days` (int), `r_squared` (float) | Weight: supply exposure; beta/lag/r² written by calibration |
| `REQUIRES` | Company | Commodity | `volume` (int) | Annual consumption volume in arbitrary units |
| `IMPACTS` | Event | Company or Commodity | `impact_time` (ISO timestamp) | Written by EventIngestor |

### Edge Population Sources

DEPENDS_ON edges are populated through three mechanisms: (1) the **seed script** pre-loads **64** curated edges based on public supply chain disclosures for S&P 500 top-50 companies; (2) the **EDGAR integration** writes additional edges from 10-K supplier disclosures tagged with `source='EDGAR'`; (3) the **causal calibrator** enriches existing edges with `beta`, `lag_days`, and `r_squared` fields computed from OLS regression over 2-year price histories.

### Example Multi-Hop Traversal

A TSMC factory disruption at `max_hops=3` propagates as follows (representative subset from seed data):

```
Hop 1 (direct dependents of TSMC):
  AAPL   weight=0.95  → Apple: critical TSMC customer (A-series, M-series chips)
  NVDA   weight=0.98  → NVIDIA: near-exclusive TSMC dependency (5nm/4nm GPU wafers)
  AMD    weight=0.95  → AMD: TSMC for all Zen 4 / RDNA 4 production
  QCOM   weight=0.90  → Qualcomm: Snapdragon on TSMC advanced nodes
  INTC   weight=0.10  → Intel: partial TSMC engagement (Meteor Lake)

Hop 2 (dependents of hop-1 companies):
  MSFT   via NVDA (0.70) → Azure AI infrastructure
  META   via NVDA (0.80) → LLaMA training clusters
  AMZN   via NVDA (0.65) → AWS Trainium/Inferentia
  GOOGL  via NVDA (0.60) → TPU programme (partial NVDA exposure)
  TSLA   via TSMC (0.50) → Full Self-Driving chip (FSD)

Hop 3 (dependents of hop-2 companies):
  JPM    via MSFT (0.45) → Azure cloud dependency
  GS     via MSFT (0.40) → Microsoft productivity + cloud
```

### Blast Radius Computation

The `trace_impact()` method executes a single parameterised Cypher query:

```cypher
MATCH path = (source:Company {ticker: $ticker})-[:DEPENDS_ON*1..{max_hops}]->(dep:Company)
WHERE dep.ticker <> $ticker
RETURN DISTINCT dep.ticker AS ticker, dep.name AS name, dep.sector AS sector,
       relationships(path)[-1].beta      AS beta,
       relationships(path)[-1].lag_days  AS lag_days,
       relationships(path)[-1].r_squared AS r_squared
```

The `{max_hops}` integer is validated in Python before interpolation. The result set contains all distinct downstream companies reachable within the hop limit, deduplicated by ticker. The causal properties (`beta`, `lag_days`, `r_squared`) of the last edge on the shortest path are attached to each result row.

---

## 9. Multi-Agent Reasoning — Deep Dive

### Agent Roles and Tools

| Agent | Stance | Tools Called | Starting Confidence | Output |
|---|---|---|---|---|
| Bull | Upside (constructive) | `get_quote` (hops=N/A), `trace_impact` (hops=2), `analyze_news_impact` (conditional) | 0.35 | `AgentOutput(stance="bull", reasoning, signals, confidence, metadata)` |
| Bear | Downside (risk-first) | `trace_impact` (hops=3), `analyze_news_impact` (conditional) | 0.40 | `AgentOutput(stance="bear", reasoning, signals, confidence, metadata)` |
| Judge | Synthesis (deterministic) | None — pure computation | — | `JudgeVerdict(verdict, conviction, composite_confidence, ...)` |

### Concurrent Execution Model

Despite the adversarial framing, bull and bear do **not** run concurrently — the bear agent receives the bull's output (specifically `metadata["weakest_claim"]`) as input to enable targeted attack. The sequence is: bull → bear (sequential); bull rebuttal → judge (sequential). The orchestrator uses `await` at each step. The SSE streaming handler mirrors this sequence, emitting events at each boundary.

### Bull Confidence Construction

```
base_confidence = 0.35
+ 0.12  if live quote retrieved successfully
+ 0.12  if graph returns ≥1 downstream dependent (hops=2)
+ 0.08  if news returns ≥1 disruption event
+ 0.06  if news returns ≥1 cascade company
= max 0.73 (before clamp to [0.0, 0.95])
```

### Bear Confidence Construction

```
base_confidence = 0.40
+ 0.08  if attack_target extracted from bull metadata
+ 0.15  if graph returns ≥1 downstream dependent (hops=3)
+ 0.08  if news returns ≥1 disruption event
+ 0.06  if news returns ≥1 cascade company
= max 0.77 (before clamp to [0.0, 0.95])
```

### Rebuttal Mechanism

The `_generate_rebuttal()` function is deterministic. It receives `bull_case.confidence`, `bear_case.confidence`, and `bear_case.metadata["attack_target"]`. If `bull_confidence ≥ bear_confidence × 0.85`, the bull maintains its thesis verbatim. Otherwise, the bull concedes the targeted claim and defends the remaining signals. No LLM call is involved.

### Judge Decision Logic

The judge (`run_judge_agent`) normalises both confidence values to the 0–100 scale. The verdict is computed as follows:

| Condition | Verdict | Conviction |
|---|---|---|
| `gap ≥ 15.0` AND `max(bull, bear) ≥ 45.0` AND `bull > bear` | `STRONG BUY` | `HIGH` |
| `gap ≥ 8.0` AND `max(bull, bear) ≥ 45.0` AND `bull > bear` | `BUY` | `MODERATE` |
| `gap ≥ 15.0` AND `max(bull, bear) ≥ 45.0` AND `bear > bull` | `STRONG SELL` | `HIGH` |
| `gap ≥ 8.0` AND `max(bull, bear) ≥ 45.0` AND `bear > bull` | `SELL` | `MODERATE` |
| `gap < 8.0` AND `bull ≥ 50.0` AND `bear ≥ 50.0` | `HOLD` | `LOW - Genuinely contested thesis` |
| `max(bull, bear) < 45.0` | `INSUFFICIENT DATA` | `VERY LOW - More data required` |
| Otherwise | `HOLD` | `LOW` |

Where `gap = abs(bull_confidence - bear_confidence)`.

**Composite confidence formula:**

```
composite_confidence = min((max_conf × 0.65) + (gap × 0.35), 95.0)
```

This rewards both absolute conviction and the size of the gap between the two sides.

The judge additionally extracts **3 bull drivers** and **3 bear drivers** from the agent signals and analysis text, and generates a three-sentence summary incorporating the verdict, dominant signal, dominant risk, and the rebuttal outcome.

### SSE Streaming Step Sequence

The `/stream/analysis` SSE endpoint emits the following event sequence:

```
{step: "init",       message: "Starting analysis for {ticker}..."}
{step: "bull_thesis", message: "Building bull thesis...", data: {}}
{step: "bull_thesis", message: "Bull case forming...",   data: {confidence, signals[:3], weakest_claim}}
{step: "bear_attack", message: "Bear agent attacking...", data: {attack_target}}
{step: "rebuttal",   message: "Bull rebuttal...",        data: {rebuttal, confidence_delta}}
{step: "judge",      message: "Judge evaluating...",     data: {}}
{step: "verdict",    message: "Verdict ready",           data: <full result object>}
{step: "done"}
```

### Verdict Persistence and Accuracy Methodology

Every verdict is persisted via `record_verdict()` immediately after the judge completes. The accuracy check is defined as: for BUY/STRONG BUY, the price must increase by more than **2%** within the window; for SELL/STRONG SELL, the price must decrease by more than **2%**. This threshold filters out noise moves and focuses accuracy on economically meaningful direction changes.

---

## 10. Quantitative Summary

The following table consolidates all hard numbers extracted directly from the codebase. It is intended for direct reference in research paper tables.

| Category | Metric | Value | Source |
|---|---|---|---|
| **Graph Scale** | Company vertices | **57** | `scripts/seed_production_data.py: len(COMPANIES)` |
| | Commodity vertices | **20** | `scripts/seed_production_data.py: len(COMMODITIES)` |
| | DEPENDS_ON edges (seed) | **64** | `seed_production_data.py: _count_unique_pairs(DEPENDS_ON_EDGES)` |
| | REQUIRES edges (seed) | **53** | `seed_production_data.py: _count_unique_pairs(REQUIRES_EDGES)` |
| | Pre-seeded historical events | **8** | `seed_production_data.py: len(HISTORICAL_EVENTS)` |
| | IMPACTS edges (seed) | **39** | Sum of entity counts across 8 events |
| | Max traversal hops | **5** | `capabilities.json: max_hops.maximum` |
| **Multi-Agent Config** | Reasoning agents | **3** (bull, bear, judge) | `src/finance_mcp/reasoning/` |
| | Debate rounds | **4** (bull → bear → rebuttal → judge) | `orchestrator.py` |
| | Bull base confidence | **0.35** | `bull_agent.py` |
| | Bear base confidence | **0.40** | `bear_agent.py` |
| | STRONG threshold (gap) | **15.0** | `judge_agent.py: STRONG_THRESHOLD` |
| | LEAN threshold (gap) | **8.0** | `judge_agent.py: LEAN_THRESHOLD` |
| | Min directional confidence | **45.0%** | `judge_agent.py: MIN_CONFIDENCE_FOR_DIRECTIONAL` |
| | Composite confidence cap | **95.0%** | `judge_agent.py: _compute_verdict()` |
| | Verdict categories | **6** (STRONG BUY, BUY, HOLD, SELL, STRONG SELL, INSUFFICIENT DATA) | `judge_agent.py` |
| | Accuracy correctness threshold | **2%** price move | `tracker.py: _is_correct()` |
| **Cache Parameters** | Qdrant similarity threshold | **0.86** | `config.py: semantic_cache_threshold` |
| | Qdrant recency window | **5 minutes** | `config.py: semantic_cache_recency_minutes` |
| | Qdrant embedding model | **all-MiniLM-L6-v2** | `qdrant_client.py: EMBEDDING_MODEL` |
| | Qdrant vector dimensions | **384** | `qdrant_client.py: VECTOR_SIZE` |
| | Redis market indices TTL | **300 seconds** | `server.py: /market/indices` |
| | Redis crypto quote TTL | **30 seconds** | `server.py: /market/crypto/{symbol}` |
| | GPT-4o context window | **20 turns** | `chat_agent.py: _history_window()` |
| **API Rate Limits** | Finnhub free tier | **60 calls/minute** | `connectors/finnhub.py: docstring` |
| | Finnhub min interval | **1.0 second** | `connectors/finnhub.py: _min_interval` |
| | Alpha Vantage free tier | **5 calls/minute** (500/day) | `connectors/alpha_vantage.py: docstring` |
| | Alpha Vantage min interval | **12.0 seconds** | `connectors/alpha_vantage.py: _min_interval` |
| | Server rate limit | **60 req / 60-second window** | `server.py: RATE_LIMIT_*` |
| | EDGAR fair-access min delay | **0.12 seconds** | `edgar_client.py: _MIN_DELAY` |
| **Causal Model** | OLS lag search range | **1–30 trading days** | `beta_calculator.py: _DEFAULT_MAX_LAG` |
| | Price history window | **2 years** | `price_fetcher.py: _DEFAULT_YEARS` |
| | Min common observations | **60 trading days** | `beta_calculator.py: max_lag + _MIN_OBS_BUFFER` |
| | Edge fields written | **3** (beta, lag_days, r_squared) | `capabilities.json: trace_impact outputSchema` |
| | Causality test | **Granger F-test** | `beta_calculator.py: grangercausalitytests` |
| **EDGAR Integration** | Max filing text per section | **12,000 characters** | `edgar_client.py: _MAX_SECTION_CHARS` |
| | Total max filing text sent | **24,000 characters** | `supplier_extractor.py: _MAX_FILING_CHARS` |
| | Extraction model temperature | **0.0** | `supplier_extractor.py: temperature=0.0` |
| | Evidence quote max length | **120 characters** | `supplier_extractor.py: _USER_PROMPT` |
| **Verdict Tracking** | SQLite table fields | **11** | `verdict_history/db.py: _DDL` |
| | 5-day accuracy check delay | **5 × 86,400 seconds** | `tracker.py: _TRADING_DAY_SECONDS × 5` |
| | 30-day accuracy check delay | **30 × 86,400 seconds** | `tracker.py: _TRADING_DAY_SECONDS × 30` |
| **MCP Tools** | Tool count | **6** | `capabilities.json` |
| | Chat agent functions | **5** (stream not exposed to chat) | `chat_agent.py: _build_tools()` |
| **API Surface** | HTTP endpoints | **14** | `mcp_server/server.py` |
| | Supported crypto symbols | **7** (BTC, ETH, BNB, SOL, XRP, ADA, DOGE) | `server.py: CRYPTO_SYMBOLS` |
| **Frontend** | Pages | **6** (Home, Landing, Chat, Dashboard, Login, SignUp) | `frontend/src/pages/` |
| | Analysis card components | **6** (Verdict, Bull, Bear, MarketData, Insights, Container) | `frontend/src/components/analysis/` |
| **Codebase Size** | Python files | **72** | `find` (excl. venv, node_modules) |
| | Total Python lines | **12,594** | `wc -l` |
| | Test files | **13** | `find tests/ -name "test_*.py"` |
| | Tests passing (unit) | **260** | `pytest -m "not integration"` |
| **Tech Versions** | Python | **3.11** | Runtime |
| | FastAPI | **0.104** | `requirements.txt` |
| | React | **19** | `frontend/package.json` |
| | TypeScript | **4.9** | `frontend/package.json` |

---

## 11. Security Model

### Authentication

Every HTTP endpoint except `GET /health` and `GET /.well-known/mcp` requires the `X-API-Key` header. The value is compared against the `MCP_API_KEY` environment variable using a direct string equality check (`api_key == settings.mcp_api_key`). Missing or incorrect keys return HTTP 401. The SSE endpoint (`/stream/analysis`) accepts the key as a query parameter (`?api_key=`) because the browser EventSource API cannot send custom headers; the same equality check applies.

### Rate Limiting

Each API key maintains an independent sliding-window deque with `maxlen=60`. On each request, timestamps older than 60 seconds are evicted from the front of the deque via `popleft()` in O(1) time. If the deque length reaches 60, the request is rejected with HTTP 429 before any tool execution occurs.

### CORS Policy

The CORSMiddleware is configured with `allow_origins=settings.allowed_origins`, which is a comma-separated list loaded from the `ALLOWED_ORIGINS` environment variable. Wildcards are not permitted. The `OPTIONS` preflight handler explicitly checks that the request origin is present in `settings.allowed_origins` before returning `Access-Control-Allow-Origin`.

### Cypher Injection Prevention

All Memgraph queries in `GraphClient` use the neo4j Python driver's parameterised query API (`session.run(query, **params)`). User-supplied values are never string-interpolated into Cypher. The sole f-string in query construction interpolates the `max_hops` integer, which has been validated as a Python `int` in `[1, 5]` before use — a bounded integer cannot carry injection payloads. Vertex IDs (tickers, commodity IDs, event IDs) are additionally validated against `^[A-Za-z0-9_.\-]{1,64}$` at the public API boundary of every `GraphClient` method.

### EDGAR SSRF Mitigation

EDGAR fetch URLs are constructed exclusively from structured fields: the CIK (a resolved 10-digit integer) and the accession number (a formatted string from the EDGAR submissions API). Neither field originates from user-controlled free-text. The ticker, which does originate from user input, is only used to look up the CIK from the EDGAR company tickers index — it is never embedded into a URL.

### GPT-4o Output Validation Before Graph Writes

The EDGAR extractor calls GPT-4o with `response_format={"type": "json_object"}` to enforce structured output. The returned JSON is parsed with `json.loads` and each item is field-validated: `supplier_ticker` is truncated to 64 characters and uppercased; `supplier_name` is truncated to 256 characters; `relationship_type` must be exactly `"supplier"` or `"customer"`; `dependency_strength` is clamped to `[0.0, 1.0]`; `evidence_quote` is truncated to 200 characters. Items where the supplier ticker equals the queried company's ticker are excluded (self-reference guard). Any item failing validation is silently skipped rather than causing a graph write error.

---

## 12. Operational Characteristics

### Startup Sequence and Dependency Order

The FastAPI lifespan handler (`@asynccontextmanager async def lifespan`) initialises components in the following order on server start:

1. `RedisClient.connect()` — establishes the Redis connection; logs a warning on failure but does not abort startup.
2. `SemanticCacheClient.initialize()` — creates the Qdrant collection if absent; warns on failure.
3. `initialize_db(settings.verdict_db_path)` — creates the SQLite `verdicts` table if absent; warns on failure.

Memgraph connectivity is tested lazily on first graph request rather than at startup. The server enters a degraded state (reported in `GET /health`) if Redis, Qdrant, or Memgraph are unavailable, but continues to serve requests that do not require the degraded component.

### Health Check Coverage

`GET /health` performs live connectivity checks against four services:

- **Redis:** `RedisClient.is_connected()` → `PING` command
- **Memgraph:** `GraphClient(host, port).__enter__()` + `client.ping()` → `RETURN 1 AS ok`
- **Qdrant:** `SemanticCacheClient.health()` → `get_collections()`
- **OpenAI:** Presence of `settings.openai_api_key` (key presence only; no API call made)

The response includes a `components` map with per-service `{status, error?}` objects and a top-level `status` field that is `"ok"` only if all four pass, `"degraded"` otherwise. HTTP 503 is returned when degraded.

### Seed Script Behaviour

`scripts/seed_production_data.py` uses Cypher `MERGE` semantics for all writes, making it safe to re-run against a populated graph without creating duplicate vertices or edges. The `--dry-run` flag prints expected counts without executing any graph writes. The script prints per-category counts on completion for verification.

### E2E Smoke Test Pipeline

`scripts/e2e_pipeline.py` validates the full data path in four steps:

1. **Full pipeline:** NewsClient → EventParser → EventIngestor → Memgraph; asserts `PipelineResult` is non-null and `articles_fetched > 0`.
2. **Graph verification:** `GraphClient.fetch_event()` on the first written event; asserts non-empty dict and correct `severity` value.
3. **Trace impact:** `GraphClient.trace_impact("TSMC", max_hops=2)`; asserts list return, presence of `ticker`/`name`/`sector` keys, no duplicates.
4. **Architecture trace:** End-to-end execution from headline through news fetch, event parse, graph write, and causal trace, with human-readable output.

---

## 13. Limitations & Future Work

### Current Limitations

**Graph coverage.** The seed graph covers the S&P 500 top 50 by market capitalisation, representing a curated but limited sample of global supply chains. Mid-cap, non-US, and private company relationships are absent from the base graph. EDGAR integration extends coverage for US-listed companies, but non-US companies (TSMC, Samsung, ASML, CATL) require manual seeding.

**Market data API constraints.** The Finnhub free tier permits 60 requests per minute; the Alpha Vantage free tier permits only 5 per minute with a 500-per-day ceiling. Heavy concurrent usage will exhaust these quotas, falling back to cached data or returning errors. Production deployment would require paid API tiers.

**LLM extraction accuracy for EDGAR relationships.** GPT-4o extracts supplier/customer relationships from 10-K text with `temperature=0.0`, but accuracy depends on the specificity of the filing language. Companies that describe suppliers in vague terms ("leading semiconductor manufacturer") without naming them will produce no extracted relationships. The evidence quote validation (120-char cap) provides an auditability signal but does not guarantee accuracy.

**Verdict accuracy evaluation lag.** The 5-day and 30-day accuracy windows use calendar-day sleep durations (`5 × 86,400 seconds`) rather than actual trading calendar days. This introduces minor measurement error around weekends and market holidays. The 2% directional threshold is conservative and may understate accuracy for high-conviction verdicts on volatile instruments.

**LLM non-determinism.** While `temperature=0.1` is used for the chat agent and `temperature=0.0` for EDGAR extraction, GPT-4o responses retain some non-determinism at these settings. The judge and rebuttal are fully deterministic, but bull and bear reasoning strings vary across runs for the same inputs.

### Potential Enhancements

- **Expanded graph coverage:** Integration of additional data sources (FactSet, Refinitiv supply chain data) to extend beyond S&P 50.
- **Alternative LLMs:** Anthropic Claude or open-weight models for EDGAR extraction to reduce OpenAI API dependency.
- **Real-time graph updates:** Streaming EDGAR 8-K filings (current reports) via EDGAR's EDGAR Full-Text Search API for intraday graph updates.
- **Options market data:** Implied volatility and put/call ratio integration as additional signals for the bear agent.
- **Expanded causal model:** Multivariate VAR models to capture inter-sector contagion, beyond pairwise OLS.
- **Production rate limiting:** Redis-backed distributed rate limiting to support multi-instance deployments.

---

## 14. Glossary

| Term | Definition |
|---|---|
| **MCP (Model Context Protocol)** | A standardised protocol for exposing typed tool schemas to AI models, enabling deterministic tool routing. QuantVex implements MCP over HTTP with JSON request/response schemas. |
| **Causal beta** | The OLS regression coefficient from an upstream supplier's log return to a downstream dependent's log return at the optimal lag. A beta of 0.8 indicates that a 1% return shock in the upstream company predicts a 0.8% return change in the downstream company after `lag_days` trading days. |
| **Blast radius** | The set of all companies reachable from a disrupted node within `max_hops` DEPENDS_ON traversal steps. A larger blast radius indicates a more systemically important supplier. |
| **DEPENDS_ON edge** | A directed graph edge from a downstream company (dependent) to an upstream company (supplier), weighted by supply exposure in [0.0, 1.0]. After causal calibration, the edge additionally carries `beta`, `lag_days`, and `r_squared`. |
| **Causal lag** | The number of trading days (`lag_days`) at which the OLS regression between upstream and downstream returns achieves maximum R². Represents the typical delay between a supplier shock and its price effect on the dependent. |
| **Verdict conviction** | A qualitative label attached to each judge verdict: HIGH (gap ≥ 15 points), MODERATE (gap ≥ 8 points), LOW (gap < 8 points or fallback). Conviction reflects the decisiveness of the debate outcome rather than the absolute confidence level. |
| **Semantic cache** | A Qdrant vector database layer that stores query embeddings and their cached responses. A new query is served from cache if its cosine similarity to a stored query exceeds 0.86 and the stored entry is within the 5-minute recency window. |
| **OLS regression** | Ordinary Least Squares regression. In the causal calibration context, OLS is applied to the model `downstream_return(t) = α + β × upstream_return(t - lag) + ε` for each lag in [1, 30]. The lag that maximises R² is selected. |
| **Supply chain hop** | A single traversal of a DEPENDS_ON edge in the Memgraph graph. A `max_hops=2` traversal finds all companies reachable within two consecutive supplier relationships from the source node. |
| **SSE streaming** | Server-Sent Events: a unidirectional HTTP streaming protocol where the server pushes `data:` frames to the client. QuantVex uses SSE to expose individual reasoning steps (bull thesis, bear attack, rebuttal, judge verdict) as they complete, enabling real-time frontend rendering of the adversarial debate. |
| **Composite confidence** | The judge's single confidence score, computed as `min((max_conf × 0.65) + (gap × 0.35), 95.0)`. It rewards both a high absolute confidence ceiling and a large gap between the two sides of the debate, capped at 95% to prevent overconfidence. |
| **Granger causality** | A statistical test that assesses whether past values of an upstream time series improve the forecast of a downstream time series beyond the downstream's own history. QuantVex uses the Granger F-test (via statsmodels) at the selected `lag_days` to produce a p-value for each calibrated DEPENDS_ON edge. |

---

## 15. References & Attribution

### Third-Party APIs and Services

| Service | Role | Documentation |
|---|---|---|
| OpenAI GPT-4o | Chat agent, EDGAR extraction, multi-agent reasoning | https://platform.openai.com/docs |
| Finnhub | Primary equity quote provider | https://finnhub.io/docs/api |
| Alpha Vantage | Fallback equity quote provider | https://www.alphavantage.co/documentation/ |
| Binance REST & WebSocket | Cryptocurrency quotes and streams | https://binance-docs.github.io/apidocs/spot/en/ |
| NewsData.io | Real-time news articles | https://newsdata.io/documentation |
| SEC EDGAR | 10-K filing retrieval, CIK resolution | https://www.sec.gov/developer |
| Yahoo Finance (v8 chart API) | NIFTY 50, SENSEX market indices (unofficial) | — |
| Open Exchange Rates | USD/INR FX rate | https://openexchangerates.org/documentation |

### Key Libraries and Frameworks

| Library | Version | Role |
|---|---|---|
| FastAPI | 0.104 | HTTP server framework |
| Pydantic / pydantic-settings | 2.x | Data validation, settings management |
| openai | 1.x | GPT-4o API client (async) |
| neo4j | 5.x | Memgraph Bolt driver |
| httpx | — | Async HTTP client for connectors |
| aiohttp | — | Async HTTP client for market index endpoints |
| redis | — | Redis Python client |
| qdrant-client | — | Qdrant vector database SDK |
| sentence-transformers | — | all-MiniLM-L6-v2 embedding model |
| yfinance | — | Historical price data for causal calibration |
| statsmodels | — | OLS regression and Granger causality |
| numpy / pandas | — | Numerical computation for calibration |
| tenacity | — | Retry logic with exponential backoff |
| React | 19 | Frontend SPA framework |
| TypeScript | 4.9 | Frontend type safety |
| Tailwind CSS | 3 | Frontend styling |
| Framer Motion | — | Frontend animation |
| Recharts | — | Frontend charting |

### Dataset Sources

| Dataset | Content | Source |
|---|---|---|
| S&P 500 top-50 supply chain relationships | 64 DEPENDS_ON edges, 53 REQUIRES edges | Manually curated from public earnings calls, 10-K filings, and supply chain research reports |
| Historical disruption events | 8 pre-seeded events (Taiwan Strait, OPEC, Suez, Rare Earth, Lithium, AI chips, Neon gas, EU gas) | Publicly documented market events; severity ratings are system-defined |
| SEC EDGAR 10-K filings | Live supplier/customer relationship extraction | U.S. Securities and Exchange Commission public EDGAR database |

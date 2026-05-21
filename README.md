<div align="center">

# QuantVex

### AI-Powered Financial Intelligence Platform

**Real-time market data · Supply chain causality · Live news ingestion · Multi-agent reasoning**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-4.9-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat-square&logo=openai&logoColor=white)](https://openai.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Overview

QuantVex is a full-stack financial intelligence platform that combines real-time market data, graph-based supply chain causality, live news ingestion, and adversarial multi-agent reasoning to deliver structured, auditable market impact analysis.

Unlike generic AI assistants, every QuantVex response is grounded in real tool calls — live quotes from market APIs, graph traversals over a supply chain knowledge graph, and freshly fetched news — never unverified LLM speculation.

```
User query → GPT-4o selects tool → tool executes against live data/graph/news
           → structured result → GPT-4o formats response → frontend renders cards
```

---

## Key Features

**Real-Time Market Data**

- Live stock quotes with multi-provider fallback (Finnhub → Alpha Vantage → Redis cache)
- Crypto prices via Binance WebSocket and REST API
- Indian market indices (NIFTY 50, SENSEX) and live USD/INR FX rate
- Two-level cache: Redis snapshot + Qdrant semantic cache

**Supply Chain Causality Graph**

- Memgraph knowledge graph with 57 companies, 20 commodities, 100+ dependency edges
- Multi-hop traversal to find all downstream companies exposed to a disruption
- Pre-seeded with real S&P 500 top-50 supply chain relationships
- **Causal beta calibration** — OLS-fitted lag models on DEPENDS_ON edges (via yfinance)

**SEC EDGAR Integration**

- Fetches the most recent 10-K filing for any US-listed company
- GPT-4o extracts named supplier/customer relationships from Business and Risk Factors sections
- Writes relationships to the graph as DEPENDS_ON edges tagged `source='EDGAR'`

**Live News Ingestion & Impact Analysis**

- Fetches real-time articles via NewsData.io
- Parses disruption events and writes them into the supply chain graph
- Computes cascade impact: which companies are affected and how far the blast radius extends

**Multi-Agent Investment Reasoning**

- Bull agent and Bear agent run concurrently, each gathering evidence from live tools
- Bull rebuttal round challenges the bear case before the judge evaluates
- Judge agent synthesises both theses into a decisive verdict: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
- Structured output renders as visual cards in the frontend
- SSE streaming exposes each reasoning step in real time as it happens
- **Verdict history** — every verdict is persisted to SQLite and accuracy-checked 5 and 30 trading days later

**AI Chat Interface**

- GPT-4o with strict domain guardrails — finance only, no off-topic answers
- Full conversation history with 20-turn rolling context window
- Deterministic tool routing: the model cannot answer news questions from memory

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        React Frontend                        │
│   HomePage · ChatPage · DashboardPage · Analysis Cards       │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS + X-API-Key
┌────────────────────────▼────────────────────────────────────┐
│                    FastAPI MCP Server (v2.0)                  │
│  /chat · /invoke · /stream/analysis · /health · /verdicts    │
│                   GPT-4o Chat Agent                          │
│         Tool routing · Conversation history · Guardrails     │
└──┬──────────────┬───────────────┬──────────────┬────────────┘
   │              │               │              │
   ▼              ▼               ▼              ▼
Market         Supply          News           Multi-Agent
Connectors     Chain Graph     Pipeline       Reasoning
   │              │               │              │
Finnhub        Memgraph       NewsData.io    Bull Agent
Alpha Vantage  (57 companies  EventParser    Bear Agent
Binance WS     20 commodities EventIngestor  Judge Agent
               100+ edges)    EDGAR 10-K     Verdict SQLite
   │              │               │              │
   └──────────────┴───────────────┴──────────────┘
                         │
              ┌──────────▼──────────┐
              │      Cache Layer     │
              │  Redis · Qdrant      │
              └─────────────────────┘
```

---

## Tech Stack

| Layer              | Technology                                                  |
| ------------------ | ----------------------------------------------------------- |
| AI Reasoning       | OpenAI GPT-4o (function calling)                            |
| Backend            | FastAPI 0.104, Python 3.11, Uvicorn                         |
| Supply Chain Graph | Memgraph (Bolt/Cypher, neo4j Python driver)                 |
| Semantic Cache     | Qdrant + sentence-transformers (all-MiniLM-L6-v2)           |
| Hot Cache          | Redis 7                                                     |
| Market Data        | Finnhub REST, Alpha Vantage REST, Binance WebSocket         |
| News               | NewsData.io REST API                                        |
| SEC Filings        | SEC EDGAR REST API (10-K filing extraction)                 |
| Causal Analytics   | yfinance + OLS (scipy/numpy)                                |
| Verdict Tracking   | SQLite                                                      |
| Frontend           | React 19, TypeScript, Tailwind CSS, Framer Motion, Recharts |
| Containerisation   | Docker Compose                                              |

---

## Project Structure

```
quantvex/
├── mcp_server/                 # FastAPI server + GPT-4o chat agent
│   ├── server.py               # All HTTP endpoints
│   ├── chat_agent.py           # GPT-4o agent with tool calling
│   ├── capabilities.json       # MCP tool catalog
│   ├── schemas.py              # Pydantic request/response models
│   ├── config.py               # Env-driven settings (pydantic-settings)
│   └── invoke_handlers/        # One handler per MCP tool
│       ├── quote_latest.py
│       ├── quote_stream.py
│       ├── trace_impact.py
│       ├── news_analysis.py
│       ├── multi_agent_analysis.py
│       ├── edgar_refresh.py    # SEC EDGAR 10-K → graph update
│       └── stream_analysis.py  # SSE streaming handler
│
├── src/finance_mcp/            # Core domain engine
│   ├── graph/
│   │   └── client.py           # GraphClient — Bolt/Cypher, injection-safe, connection-pooled
│   ├── news/                   # News ingestion pipeline
│   │   ├── news_client.py      # NewsData.io adapter
│   │   └── event_parser.py     # Rule-based disruption parser
│   ├── ingestion/              # Graph write layer
│   │   ├── event_ingestor.py   # Writes Event vertices + IMPACTS edges
│   │   └── pipeline.py         # End-to-end orchestration
│   ├── reasoning/              # Multi-agent reasoning
│   │   ├── bull_agent.py       # Upside thesis agent
│   │   ├── bear_agent.py       # Downside thesis agent
│   │   ├── judge_agent.py      # Verdict synthesis
│   │   ├── orchestrator.py     # Concurrent bull/bear execution + rebuttal
│   │   └── schemas.py          # Agent I/O contracts
│   ├── edgar/                  # SEC EDGAR integration
│   │   ├── edgar_client.py     # EDGAR HTTP client (CIK lookup + 10-K fetch)
│   │   ├── supplier_extractor.py # GPT-4o relationship extraction
│   │   └── graph_updater.py    # Writes DEPENDS_ON edges to graph
│   ├── causal/                 # Causal beta calibration
│   │   ├── price_fetcher.py    # yfinance price history download
│   │   ├── beta_calculator.py  # OLS lag model
│   │   └── calibrator.py       # Full-graph calibration orchestrator
│   ├── verdict_history/        # Verdict accuracy tracking
│   │   ├── db.py               # SQLite schema + connection helpers
│   │   ├── tracker.py          # record_verdict + async 5d/30d price checks
│   │   └── accuracy.py         # Accuracy stats aggregation
│   └── services/               # Shared business logic
│       ├── quote_service.py
│       ├── graph_service.py
│       └── news_service.py
│
├── connectors/                 # Market data adapters
│   ├── finnhub.py              # REST quote + profile (60 req/min)
│   ├── alpha_vantage.py        # REST quote/intraday (5 req/min)
│   └── binance_ws.py           # Live WebSocket trade stream
│
├── cache/                      # Cache layer
│   ├── redis_client.py         # Snapshot + stream APIs
│   └── qdrant_client.py        # Semantic cache with similarity threshold
│
├── frontend/                   # React application
│   └── src/
│       ├── pages/              # HomePage · ChatPage · DashboardPage
│       ├── components/
│       │   ├── analysis/       # VerdictCard · BullCaseCard · BearCaseCard
│       │   └── ui/             # AnimatedHero · AnimatedAIChat · FocusRail
│       └── services/api.ts     # Typed Axios API client
│
├── tests/                      # Unit + integration tests
├── scripts/                    # Ops scripts
│   ├── seed_production_data.py # Seeds full S&P 50 + commodities graph
│   ├── verify_system.py        # System health verification
│   └── e2e_pipeline.py         # End-to-end smoke test
│
├── infra/                      # Docker Compose (Redis, Qdrant, MCP server)
└── docker/                     # Memgraph Docker Compose
```

---

## MCP Tools

QuantVex exposes six tools through its Model Context Protocol server:

| Tool                   | Description                                                                               |
| ---------------------- | ----------------------------------------------------------------------------------------- |
| `quote.latest`         | Live stock/crypto price with cache waterfall and provider fallback                        |
| `quote.stream`         | Subscribe to real-time Binance WebSocket price stream                                     |
| `trace_impact`         | Multi-hop supply chain traversal — finds all downstream companies exposed to a disruption |
| `analyze_news_impact`  | Fetch live news → parse events → write to graph → return cascade impact                   |
| `multi_agent_analysis` | Run concurrent bull/bear reasoning and return a judge verdict                             |
| `edgar_refresh`        | Fetch SEC 10-K → extract suppliers via GPT-4o → update graph edges                       |

---

## API Reference

All endpoints require `X-API-Key` header except `/health` and `/.well-known/mcp`.

| Method | Endpoint                   | Description                                   |
| ------ | -------------------------- | --------------------------------------------- |
| `GET`  | `/.well-known/mcp`         | MCP discovery metadata                        |
| `GET`  | `/capabilities`            | Full tool catalog with schemas                |
| `POST` | `/invoke`                  | Execute any MCP tool by name                  |
| `POST` | `/chat`                    | GPT-4o conversational interface               |
| `GET`  | `/stream/analysis`         | SSE stream of multi-agent reasoning steps     |
| `POST` | `/subscribe`               | Subscribe to a live price stream              |
| `POST` | `/unsubscribe`             | Cancel a stream subscription                  |
| `GET`  | `/subscriptions`           | List active subscriptions                     |
| `POST` | `/calibrate/edges`         | Trigger background causal beta calibration    |
| `GET`  | `/verdicts/history`        | Verdict history (filterable by ticker)        |
| `GET`  | `/verdicts/accuracy`       | Per-verdict-type accuracy statistics          |
| `GET`  | `/market/indices`          | Live NIFTY 50, SENSEX, USD/INR                |
| `GET`  | `/market/crypto/{symbol}`  | Live crypto quote via Binance                 |
| `GET`  | `/health`                  | Deep health check across all services         |

### Example — Invoke a tool

```bash
curl -X POST http://localhost:8000/invoke \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "quote.latest",
    "arguments": { "symbol": "AAPL" }
  }'
```

```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "price": 213.17,
    "inr_price": 17891.45,
    "usd_inr_rate": 83.94,
    "data_source": "FINNHUB",
    "cache_hit": false,
    "latency_ms": 142.3
  }
}
```

### Example — Supply chain trace

```bash
curl -X POST http://localhost:8000/invoke \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "trace_impact",
    "arguments": { "ticker": "TSMC", "max_hops": 3 }
  }'
```

### Example — EDGAR refresh

```bash
curl -X POST http://localhost:8000/invoke \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "edgar_refresh",
    "arguments": { "ticker": "AAPL" }
  }'
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker and Docker Compose
- API keys: OpenAI, Finnhub, Alpha Vantage, NewsData.io

### 1. Clone the repository

```bash
git clone https://github.com/Anurag7010/finance-mcp.git
cd finance-mcp
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in all required values:

```env
# Required
OPENAI_API_KEY=sk-...
MCP_API_KEY=your-secret-key

# Market data
FINNHUB_API_KEY=your-finnhub-key
ALPHA_VANTAGE_API_KEY=your-av-key

# News
NEWSDATA_API_KEY=pub_...

# Infrastructure (defaults work with Docker Compose)
REDIS_HOST=localhost
REDIS_PORT=6379
QDRANT_HOST=localhost
QDRANT_PORT=6333
MEMGRAPH_HOST=localhost
MEMGRAPH_PORT=7687

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 3. Start infrastructure

```bash
# Start Redis, Qdrant, and the MCP server container
cd infra && docker-compose up -d

# Start Memgraph (required for supply chain graph)
cd docker && docker-compose -f memgraph-docker-compose.yml up -d
```

Wait ~20 seconds for services to initialise. Memgraph Lab UI is available at http://localhost:7444.

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Seed the supply chain graph

```bash
PYTHONPATH=src python scripts/seed_production_data.py
```

This seeds 57 companies, 20 commodities, 64 DEPENDS_ON edges, 53 REQUIRES edges, and 8 pre-seeded historical events into Memgraph.

### 6. Verify system health

```bash
PYTHONPATH=src python scripts/verify_system.py
```

All components should report OK.

### 7. Start the MCP server

```bash
PYTHONPATH=src uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000 --reload
```

### 8. Start the frontend

```bash
cd frontend
cp .env.example .env          # set REACT_APP_API_KEY and REACT_APP_API_URL
npm install
npm start
```

Open [http://localhost:3000](http://localhost:3000).

---

## Supply Chain Graph

The Memgraph knowledge graph represents real-world supply chain dependencies across the S&P 500 top 50. Uses Bolt protocol with the standard neo4j Python driver — fully parameterised Cypher queries throughout.

**Graph Schema**

| Vertex Type | Properties                 |
| ----------- | -------------------------- |
| `Company`   | `ticker`, `name`, `sector` |
| `Commodity` | `name`, `category`         |
| `Event`     | `description`, `severity`  |

| Edge Type    | Properties                         | Meaning                                         |
| ------------ | ---------------------------------- | ----------------------------------------------- |
| `DEPENDS_ON` | `weight`, `beta`, `lag_days`, `r_squared` | Company relies on another company as a supplier |
| `REQUIRES`   | `volume`                           | Company consumes a commodity                    |
| `IMPACTS`    | `impact_time`                      | An event affects a company or commodity         |

**Example trace**

A TSMC factory disruption propagates to:

```
TSMC → AAPL (weight: 0.95)
TSMC → NVDA (weight: 0.98)
TSMC → AMD  (weight: 0.95)
TSMC → QCOM (weight: 0.90)
NVDA → MSFT (weight: 0.70) [hop 2]
NVDA → META (weight: 0.80) [hop 2]
NVDA → AMZN (weight: 0.65) [hop 2]
```

---

## Multi-Agent Reasoning

The bull-bear-judge pipeline runs when a user requests an investment thesis.

```
User: "Give me a full analysis of NVDA"
         │
         ├── Bull Agent ──────────────────────────────────┐
         │   Gathers: live quote, trace_impact evidence    │
         │   Builds: upside thesis + confidence score      │
         │                                                 │
         └── Bear Agent                                    │
             Gathers: news impact, blast radius            │
             Builds: downside thesis + confidence score    │
                         │                                 │
                         ▼                                 │
                    Bull Rebuttal ◄──────────────────────┘
                         │
                         ▼
                    Judge Agent
                    Compares confidence gap
                    Produces: verdict + conviction
                    Returns: structured JSON
```

**Verdict scale**

| Verdict             | Condition                                         |
| ------------------- | ------------------------------------------------- |
| `STRONG BUY`        | Bull confidence gap ≥ 15 points, confidence ≥ 45% |
| `BUY`               | Bull confidence gap ≥ 8 points, confidence ≥ 45%  |
| `HOLD`              | Gap < 8 points — genuinely contested              |
| `SELL`              | Bear confidence gap ≥ 8 points                    |
| `STRONG SELL`       | Bear confidence gap ≥ 15 points                   |
| `INSUFFICIENT DATA` | Max confidence < 45%                              |

Verdicts are stored in SQLite and automatically checked for accuracy 5 and 30 trading days later using yfinance price data. Accuracy statistics are available via `/verdicts/accuracy`.

---

## Causal Beta Calibration

The `/calibrate/edges` endpoint triggers a background job that:

1. Fetches all DEPENDS_ON edges from Memgraph
2. Downloads 2 years of daily close prices via yfinance for each unique ticker
3. Fits OLS regression at lags 1–30 trading days for each supplier–dependent pair
4. Writes `beta`, `lag_days`, and `r_squared` onto each edge

This quantifies _how much_ and _how quickly_ a supplier shock transmits to a downstream company.

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Unit tests only (no graph/DB required)
pytest tests/ -v -m "not integration"

# With coverage
pytest tests/ --cov=mcp_server --cov=src/finance_mcp --cov-report=term-missing
```

---

## Security

- All tool endpoints require `X-API-Key` header — returns 401 on missing/invalid key
- Rate limiting: 60 requests per 60-second window per API key — returns 429 on breach
- CORS restricted to configured `ALLOWED_ORIGINS` — no wildcard in production
- All graph queries use parameterised Cypher — no string interpolation of user input
- EDGAR URLs are constructed from structured fields (CIK, accession number) — no SSRF surface
- GPT-4o output from EDGAR extraction is JSON-parsed and field-validated before graph write
- Frontend API key loaded from environment variable, never hardcoded

---

## Environment Variables

| Variable                | Required | Description                       |
| ----------------------- | -------- | --------------------------------- |
| `OPENAI_API_KEY`        | ✅       | GPT-4o API key                    |
| `MCP_API_KEY`           | ✅       | Server authentication key         |
| `FINNHUB_API_KEY`       | ✅       | Finnhub market data               |
| `ALPHA_VANTAGE_API_KEY` | ✅       | Alpha Vantage market data         |
| `NEWSDATA_API_KEY`      | ✅       | NewsData.io real-time news        |
| `REDIS_HOST`            | ✅       | Redis hostname                    |
| `REDIS_PORT`            | ✅       | Redis port (default: 6379)        |
| `QDRANT_HOST`           | ✅       | Qdrant hostname                   |
| `QDRANT_PORT`           | ✅       | Qdrant port (default: 6333)       |
| `MEMGRAPH_HOST`         | ✅       | Memgraph hostname                 |
| `MEMGRAPH_PORT`         | ✅       | Memgraph Bolt port (default: 7687)|
| `ALLOWED_ORIGINS`       | ✅       | Comma-separated CORS origins      |
| `VERDICT_DB_PATH`       | ✗        | SQLite path (default: verdicts.db)|

---

## Operational Scripts

| Script                            | Purpose                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------ |
| `scripts/seed_production_data.py` | Seeds full S&P 50 company/commodity graph. Safe to re-run (idempotent). Supports `--dry-run`.    |
| `scripts/verify_system.py`        | Checks all service connections, graph health, handler registration, and GPT-4o access.           |
| `scripts/e2e_pipeline.py`         | Full end-to-end smoke test: news fetch → graph ingest → trace → multi-agent.                     |

---

## Development

### Adding a new MCP tool

1. Add schema entry to `mcp_server/capabilities.json`
2. Implement handler in `mcp_server/invoke_handlers/`
3. Export from `mcp_server/invoke_handlers/__init__.py`
4. Add dispatch branch in `mcp_server/server.py` `/invoke` handler
5. Add GPT-4o function declaration and `_execute_tool` mapping in `mcp_server/chat_agent.py`
6. Add tests in `tests/`

### Adding a new data source

1. Add connector module under `connectors/`
2. Add settings fields in `mcp_server/config.py` and `.env.example`
3. Integrate fallback logic in `mcp_server/invoke_handlers/quote_latest.py`
4. Add normalisation tests in `tests/test_connectors.py`

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built for finance professionals who need answers grounded in data, not guesswork.

</div>

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

- NebulaGraph knowledge graph with 57 companies, 20 commodities, 100+ dependency edges
- Multi-hop traversal to find all downstream companies exposed to a disruption
- Pre-seeded with real S&P 500 top-50 supply chain relationships

**Live News Ingestion & Impact Analysis**

- Fetches real-time articles via NewsData.io
- Parses disruption events and writes them into the supply chain graph
- Computes cascade impact: which companies are affected and how far the blast radius extends

**Multi-Agent Investment Reasoning**

- Bull agent and Bear agent run concurrently, each gathering evidence from live tools
- Judge agent synthesises both theses into a decisive verdict: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
- Structured output renders as visual cards in the frontend

**AI Chat Interface**

- GPT-4o with strict domain guardrails — finance only, no off-topic answers
- Full conversation history with 20-turn rolling context window
- Deterministic tool routing: the model cannot answer news questions from memory

**Lineage Observability**

- Every API call, agent invocation, and stream event is recorded in Neo4j
- Full audit trail of what data was used to produce each answer

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        React Frontend                        │
│   HomePage · ChatPage · DashboardPage · Analysis Cards       │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS + X-API-Key
┌────────────────────────▼────────────────────────────────────┐
│                    FastAPI MCP Server                        │
│  /chat · /invoke · /subscribe · /health · /market/indices   │
│                   GPT-4o Chat Agent                          │
│         Tool routing · Conversation history · Guardrails     │
└──┬──────────────┬───────────────┬──────────────┬────────────┘
   │              │               │              │
   ▼              ▼               ▼              ▼
Market         Supply          News           Multi-Agent
Connectors     Chain Graph     Pipeline       Reasoning
   │              │               │              │
Finnhub        NebulaGraph    NewsData.io    Bull Agent
Alpha Vantage  (57 companies  EventParser    Bear Agent
Binance WS     20 commodities EventIngestor  Judge Agent
               100+ edges)
   │              │               │              │
   └──────────────┴───────────────┴──────────────┘
                         │
              ┌──────────▼──────────┐
              │      Cache Layer     │
              │  Redis · Qdrant      │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Neo4j Lineage Graph │
              │  (Audit / Observ.)   │
              └─────────────────────┘
```

---

## Tech Stack

| Layer              | Technology                                                  |
| ------------------ | ----------------------------------------------------------- |
| AI Reasoning       | OpenAI GPT-4o (function calling)                            |
| Backend            | FastAPI 0.104, Python 3.11, Uvicorn                         |
| Supply Chain Graph | NebulaGraph (nGQL)                                          |
| Lineage Graph      | Neo4j 5 (Cypher)                                            |
| Semantic Cache     | Qdrant + sentence-transformers (all-MiniLM-L6-v2)           |
| Hot Cache          | Redis 5                                                     |
| Market Data        | Finnhub REST, Alpha Vantage REST, Binance WebSocket         |
| News               | NewsData.io REST API                                        |
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
│   ├── config.py               # Env-driven settings
│   ├── invoke_handlers/        # One handler per MCP tool
│   │   ├── quote_latest.py
│   │   ├── quote_stream.py
│   │   ├── trace_impact.py
│   │   ├── news_analysis.py
│   │   └── multi_agent_analysis.py
│   └── utils/
│       ├── logging.py          # Structlog JSON logger
│       └── validation.py       # Input guardrails
│
├── src/finance_mcp/            # Core domain engine
│   ├── graph/                  # NebulaGraph client + queries + schema
│   │   ├── client.py           # SecureGraphClient (parameterised, injection-safe)
│   │   ├── queries.py          # Immutable nGQL templates
│   │   └── schema.py           # Space/tag/edge bootstrap
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
│   │   ├── orchestrator.py     # Concurrent bull/bear execution
│   │   └── schemas.py          # Agent I/O contracts
│   └── services/               # Shared business logic (decoupled from server)
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
├── graph/                      # Neo4j lineage observability
│   ├── neo4j_client.py         # Schema + CRUD for audit nodes
│   └── lineage_writer.py       # Records every call into Neo4j
│
├── frontend/                   # React application
│   └── src/
│       ├── pages/              # HomePage · ChatPage · DashboardPage
│       ├── components/
│       │   ├── analysis/       # VerdictCard · BullCaseCard · BearCaseCard
│       │   └── ui/             # AnimatedHero · AnimatedAIChat · FocusRail
│       └── services/api.ts     # Typed Axios API client
│
├── tests/                      # 194 tests (unit + integration)
├── scripts/                    # Ops scripts
│   ├── seed_production_data.py # Seeds full S&P 50 + commodities graph
│   ├── verify_system.py        # System health verification
│   └── e2e_pipeline.py         # End-to-end smoke test
│
├── infra/                      # Docker Compose for backend services
├── docker/                     # NebulaGraph cluster compose
└── docs/                       # Architecture and fix documentation
```

---

## MCP Tools

QuantVex exposes five tools through its Model Context Protocol server:

| Tool                   | Description                                                                               |
| ---------------------- | ----------------------------------------------------------------------------------------- |
| `quote.latest`         | Live stock/crypto price with cache waterfall and provider fallback                        |
| `quote.stream`         | Subscribe to real-time Binance WebSocket price stream                                     |
| `trace_impact`         | Multi-hop supply chain traversal — finds all downstream companies exposed to a disruption |
| `analyze_news_impact`  | Fetch live news → parse events → write to graph → return cascade impact                   |
| `multi_agent_analysis` | Run concurrent bull/bear reasoning and return a judge verdict                             |

---

## API Reference

All endpoints require `X-API-Key` header except `/health` and `/.well-known/mcp`.

| Method | Endpoint                  | Description                           |
| ------ | ------------------------- | ------------------------------------- |
| `GET`  | `/.well-known/mcp`        | MCP discovery metadata                |
| `GET`  | `/capabilities`           | Full tool catalog with schemas        |
| `POST` | `/invoke`                 | Execute any MCP tool by name          |
| `POST` | `/chat`                   | GPT-4o conversational interface       |
| `POST` | `/subscribe`              | Subscribe to a live price stream      |
| `POST` | `/unsubscribe`            | Cancel a stream subscription          |
| `GET`  | `/subscriptions`          | List active subscriptions             |
| `GET`  | `/market/indices`         | Live NIFTY 50, SENSEX, USD/INR        |
| `GET`  | `/market/crypto/{symbol}` | Live crypto quote via Binance         |
| `GET`  | `/health`                 | Deep health check across all services |

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

### Example — Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "Which companies are exposed if TSMC shuts down?"}'
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

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker and Docker Compose
- API keys: OpenAI, Finnhub, Alpha Vantage, NewsData.io

### 1. Clone the repository

```bash
git clone https://github.com/your-org/quantvex.git
cd quantvex
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
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
NEBULA_HOST=localhost
NEBULA_PORT=9669

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 3. Start infrastructure

```bash
# Start Redis, Qdrant, Neo4j, MCP server
cd infra && docker-compose up -d

# Start NebulaGraph cluster (required for supply chain graph)
cd docker && docker-compose -f nebula-docker-compose.yml up -d
```

Wait ~30 seconds for all services to initialise.

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Seed the supply chain graph

```bash
python scripts/seed_production_data.py
```

This seeds 57 companies, 20 commodities, 64 DEPENDS_ON edges, 53 REQUIRES edges, and 8 pre-seeded historical events into NebulaGraph.

### 6. Verify system health

```bash
python scripts/verify_system.py
```

All components should report OK.

### 7. Start the MCP server

```bash
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000 --reload
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

The NebulaGraph knowledge graph represents real-world supply chain dependencies across the S&P 500 top 50.

**Graph Schema**

| Vertex Type | Properties                 |
| ----------- | -------------------------- |
| `Company`   | `ticker`, `name`, `sector` |
| `Commodity` | `name`, `category`         |
| `Event`     | `description`, `severity`  |

| Edge Type    | Properties     | Meaning                                         |
| ------------ | -------------- | ----------------------------------------------- |
| `DEPENDS_ON` | `weight` (0–1) | Company relies on another company as a supplier |
| `REQUIRES`   | `volume`       | Company consumes a commodity                    |
| `IMPACTS`    | `impact_time`  | An event affects a company or commodity         |

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
         │                                                 ▼
         └── Bear Agent ──────────────────────────────► Judge Agent
             Gathers: news impact, blast radius            Compares confidence gap
             Builds: downside thesis + confidence score    Produces: verdict + conviction
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

**Test suite:** 194 tests across 11 test files covering connectors, graph client security, query injection safety, event parsing, pipeline orchestration, and MCP endpoint contracts.

---

## Security

- All tool endpoints require `X-API-Key` header — returns 401 on missing/invalid key
- Rate limiting: 60 requests per 60-second window per API key — returns 429 on breach
- CORS restricted to configured `ALLOWED_ORIGINS` — no wildcard in production
- NebulaGraph uses a restricted `mcp_agent` runtime user with read-only graph access
- All graph queries use parameterised execution — injection markers are explicitly checked
- Frontend API key loaded from environment variable, never hardcoded

---

## Environment Variables

| Variable                | Required | Description                      |
| ----------------------- | -------- | -------------------------------- |
| `OPENAI_API_KEY`        | ✅       | GPT-4o API key                   |
| `MCP_API_KEY`           | ✅       | Server authentication key        |
| `FINNHUB_API_KEY`       | ✅       | Finnhub market data              |
| `ALPHA_VANTAGE_API_KEY` | ✅       | Alpha Vantage market data        |
| `NEWSDATA_API_KEY`      | ✅       | NewsData.io real-time news       |
| `REDIS_HOST`            | ✅       | Redis hostname                   |
| `REDIS_PORT`            | ✅       | Redis port (default: 6379)       |
| `QDRANT_HOST`           | ✅       | Qdrant hostname                  |
| `QDRANT_PORT`           | ✅       | Qdrant port (default: 6333)      |
| `NEO4J_URI`             | ✅       | Neo4j bolt URI                   |
| `NEO4J_USER`            | ✅       | Neo4j username                   |
| `NEO4J_PASSWORD`        | ✅       | Neo4j password                   |
| `NEBULA_HOST`           | ✅       | NebulaGraph graphd hostname      |
| `NEBULA_PORT`           | ✅       | NebulaGraph port (default: 9669) |
| `ALLOWED_ORIGINS`       | ✅       | Comma-separated CORS origins     |

---

## Operational Scripts

| Script                            | Purpose                                                                                       |
| --------------------------------- | --------------------------------------------------------------------------------------------- |
| `scripts/seed_production_data.py` | Seeds full S&P 50 company/commodity graph. Safe to re-run (idempotent). Supports `--dry-run`. |
| `scripts/verify_system.py`        | Checks all service connections, graph health, handler registration, and GPT-4o access.        |
| `scripts/e2e_pipeline.py`         | Full end-to-end smoke test: news fetch → graph ingest → trace → multi-agent.                  |

---

## Development

### Adding a new MCP tool

1. Add schema entry to `mcp_server/capabilities.json`
2. Implement handler in `mcp_server/invoke_handlers/`
3. Export from `mcp_server/invoke_handlers/__init__.py`
4. Add dispatch branch in `mcp_server/server.py` `/invoke` handler
5. Add GPT-4o function declaration and `_execute_tool` mapping in `mcp_server/chat_agent.py`
6. Add tests in `tests/` mirroring `tests/test_mcp_invoke.py`

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

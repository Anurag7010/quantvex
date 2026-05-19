# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**QuantVex** — an AI-powered financial intelligence platform. A FastAPI backend exposes an MCP (Model Context Protocol) server backed by GPT-4o with tool-calling. The frontend is a React 19/TypeScript app. Infrastructure is Docker Compose.

## Commands

### Backend

```bash
# Activate virtualenv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the MCP server (dev, with reload)
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000 --reload

# Run all tests
pytest tests/ -v

# Unit tests only (no live graph/DB required)
pytest tests/ -v -m "not integration"

# Run a single test file
pytest tests/test_mcp_invoke.py -v

# Run with coverage
pytest tests/ --cov=mcp_server --cov=src/finance_mcp --cov-report=term-missing
```

### Frontend

```bash
cd frontend
npm install
npm start        # dev server at http://localhost:3000
npm run build    # production build
```

### Infrastructure

```bash
# Start Redis, Qdrant, Neo4j (and the MCP server container)
cd infra && docker-compose up -d

# Start NebulaGraph cluster (required for supply chain graph)
cd docker && docker-compose -f nebula-docker-compose.yml up -d

# Seed the supply chain graph (57 companies, 20 commodities, 100+ edges)
python scripts/seed_production_data.py

# Verify all services are healthy
python scripts/verify_system.py

# Full end-to-end smoke test
python scripts/e2e_pipeline.py
```

## Architecture

### Request Flow

```
React frontend  →  POST /chat or /invoke  →  FastAPI (mcp_server/server.py)
                        ↓                          ↓
                  chat_agent.py             invoke_handlers/
                  (GPT-4o function           one file per tool
                   calling loop)                   ↓
                        └──────────────────→ services + connectors
                                                   ↓
                                     NebulaGraph / Redis / Qdrant / Neo4j
```

### Key Modules

| Path                               | Role                                                                                                            |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `mcp_server/server.py`             | All HTTP endpoints; auth (`X-API-Key`), rate limiting, CORS                                                     |
| `mcp_server/chat_agent.py`         | GPT-4o agent with finance domain guardrails and 20-turn history                                                 |
| `mcp_server/capabilities.json`     | MCP tool catalog (schema definitions for all five tools)                                                        |
| `mcp_server/config.py`             | All settings via `pydantic_settings`; loaded from `.env`                                                        |
| `mcp_server/invoke_handlers/`      | One file per MCP tool (`quote_latest`, `quote_stream`, `trace_impact`, `news_analysis`, `multi_agent_analysis`) |
| `src/finance_mcp/graph/client.py`  | `SecureGraphClient` — parameterised NebulaGraph queries, injection-safe                                         |
| `src/finance_mcp/graph/queries.py` | Immutable nGQL templates (never build query strings inline)                                                     |
| `src/finance_mcp/reasoning/`       | `bull_agent.py`, `bear_agent.py`, `judge_agent.py`, `orchestrator.py` — concurrent execution via asyncio        |
| `src/finance_mcp/news/`            | NewsData.io adapter + rule-based disruption event parser                                                        |
| `src/finance_mcp/ingestion/`       | Writes Event vertices + `IMPACTS` edges into NebulaGraph                                                        |
| `connectors/`                      | Market data adapters: Finnhub (primary), Alpha Vantage (fallback), Binance WebSocket                            |
| `cache/redis_client.py`            | Hot quote snapshot cache                                                                                        |
| `cache/qdrant_client.py`           | Semantic cache (sentence-transformers, threshold 0.86)                                                          |
| `frontend/src/services/api.ts`     | Typed Axios API client                                                                                          |

### Data / Cache Waterfall

Quote requests follow: **Qdrant semantic cache → Redis snapshot → Finnhub REST → Alpha Vantage REST**.

### Multi-Agent Pipeline

`orchestrator.py` runs bull and bear agents concurrently with `asyncio.gather`. Each agent calls the same live tools (quote, trace_impact, news). `judge_agent.py` compares confidence scores to emit one of: `STRONG BUY / BUY / HOLD / SELL / STRONG SELL / INSUFFICIENT DATA`.

### NebulaGraph Schema

Three vertex types (`Company`, `Commodity`, `Event`) and three edge types (`DEPENDS_ON`, `REQUIRES`, `IMPACTS`). Space is named `supply_chain`. Runtime user is `mcp_agent` (INSERT/UPDATE/DELETE + traversal only — no schema DDL).

## Adding a New MCP Tool

1. Add schema to `mcp_server/capabilities.json`
2. Implement handler in `mcp_server/invoke_handlers/<tool_name>.py`
3. Export from `mcp_server/invoke_handlers/__init__.py`
4. Add dispatch branch in `server.py` `/invoke` handler
5. Add GPT-4o function declaration + `_execute_tool` mapping in `chat_agent.py`
6. Add tests mirroring `tests/test_mcp_invoke.py`

## Key Invariants

- All NebulaGraph queries must go through `SecureGraphClient._execute()` with parameter binding — never string-interpolate nGQL.
- Graph query templates live only in `src/finance_mcp/graph/queries.py`.
- The `X-API-Key` header is required on every endpoint except `/health` and `/.well-known/mcp`.
- Rate limit is 60 requests / 60-second window per key (enforced in-memory in `server.py`).
- `ALLOWED_ORIGINS` must be set explicitly in production — the server does not allow wildcards.
- The `NEWSDATA_API_KEY` env var is the active news key; `NEWS_API_KEY` is a legacy alias also accepted.
- Neo4j has been removed entirely — do not re-add it. The `graph/` directory now only contains an empty `__init__.py`.

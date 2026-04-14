# Finance MCP

Deterministic financial intelligence system that combines MCP tool execution, supply-chain graph traversal, event ingestion, and multi-agent reasoning.

## Overview

Finance MCP is a full-stack system for market analysis.
It serves real-time quote tools, computes dependency impact through a graph model, ingests external disruption events, and synthesizes outputs through a bull/bear/judge reasoning pipeline.

The system is built to answer financial impact questions with tool-grounded responses rather than free-form model speculation.

## Key Capabilities

- Real-time quote retrieval across equities and crypto via provider fallback and cache waterfall.
- Deterministic multi-hop impact tracing over supply-chain dependencies.
- Event-driven impact analysis from live news ingestion into graph memory.
- Structured multi-agent reasoning with confidence-scored verdicts.
- Chat and dashboard frontend for analysis workflows.

## System Architecture

```
Browser (Chat/Dashboard)
        |
        v
React Frontend
        |
        v
MCP Server (FastAPI)
  |          |             |             |
  v          v             v             v
Connectors   Cache         Graph         Reasoning
(AV/FH/BN) (Redis/Qdrant) (Neo4j/Nebula) (Bull/Bear/Judge)
```

Flow summary:

1. Frontend sends a request to `/chat` or `/invoke`.
2. MCP server dispatches to a tool handler.
3. Handler reads from cache and external providers or graph stores.
4. Response is returned as structured JSON to frontend.

## Core Components

### MCP Server

`mcp_server/server.py` exposes:

- `POST /invoke` for tool execution.
- `POST /subscribe` and `POST /unsubscribe` for streaming lifecycle.
- `POST /chat` for OpenAI-driven tool orchestration.
- `GET /capabilities` and `GET /health` for discovery and checks.

Implemented tools:

- `quote.latest`
- `quote.stream`
- `trace_impact`
- `analyze_news_impact`
- `multi_agent_analysis`

### Graph Layer

- NebulaGraph (`src/finance_mcp/graph`) stores companies, dependencies, commodities, and event relationships.
- `trace_impact` executes bounded multi-hop traversal with input validation and parameterized query execution.
- Neo4j (`graph/`) stores lineage metadata for API/tool interactions.

### News Ingestion Pipeline

`src/finance_mcp/ingestion/pipeline.py` orchestrates:

- NewsAPI fetch via `NewsClient`.
- Disruption/entity extraction via `EventParser`.
- Graph writes via `EventIngestor`.

This pipeline powers `analyze_news_impact` by linking external events to downstream dependency cascades.

### Multi-Agent Reasoning Engine

`src/finance_mcp/reasoning/orchestrator.py` runs:

- Bull agent for upside thesis.
- Bear agent for risk thesis.
- Judge agent for final synthesis.

Output includes bull case, bear case, verdict, confidence, and key drivers.

### Frontend

`frontend/` provides:

- Chat experience for natural-language queries backed by MCP tools.
- Dashboard for quote retrieval and market context visualization.

## How It Works (Execution Flow)

Example query: "Which companies depend on TSMC?"

1. User submits query in chat UI.
2. Frontend calls `POST /chat`.
3. Chat agent selects and executes `trace_supply_chain_impact` tool mapping to backend `trace_impact` handler.
4. Handler validates ticker and hop bounds.
5. NebulaGraph traversal returns impacted downstream companies.
6. Chat agent formats structured response for the UI.

Example quote flow:

1. Frontend calls `POST /invoke` with `tool_name=quote.latest`.
2. Handler checks semantic cache (Qdrant), then hot cache (Redis).
3. On miss, handler falls back across providers (Finnhub, Alpha Vantage, Binance for crypto).
4. Result is returned and optionally persisted back to cache and lineage graph.

## Repository Structure

```
finance-mcp/
├── mcp_server/                 # FastAPI app, schemas, invoke handlers
├── src/finance_mcp/
│   ├── graph/                  # NebulaGraph client and queries
│   ├── ingestion/              # Event ingestion pipeline
│   ├── news/                   # News fetch + parsing
│   └── reasoning/              # Bull/Bear/Judge orchestration
├── graph/                      # Neo4j lineage writer/client
├── connectors/                 # Alpha Vantage, Finnhub, Binance integrations
├── cache/                      # Redis and Qdrant clients
├── frontend/                   # React application (chat + dashboard)
├── infra/                      # Dockerfile and core compose
├── docker/                     # NebulaGraph compose stack
├── scripts/                    # e2e and operational verification scripts
├── tests/                      # Backend/unit/integration tests
├── requirements.txt
└── README.md
```

## Setup Instructions

### Backend

1. Create environment file:

```bash
cp infra/.env.example .env
```

2. Set required keys in `.env`:

- `MCP_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `FINNHUB_API_KEY`
- `NEWS_API_KEY`
- `OPENAI_API_KEY`

3. Start infrastructure and backend:

```bash
docker compose -f infra/docker-compose.yml -f docker/nebula-docker-compose.yml up -d --build
```

4. Health check:

```bash
curl http://localhost:8000/health
```

Local Python runtime (without Docker):

```bash
source source/bin/activate
pip install -r requirements.txt
PYTHONPATH=src:. uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start
```

Default URL: `http://localhost:3000`

## API Examples

### Invoke `quote.latest`

```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{
    "tool_name": "quote.latest",
    "arguments": {"symbol": "AAPL", "maxAgeSec": 60},
    "agent_id": "cli"
  }'
```

### Invoke `trace_impact`

```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{
    "tool_name": "trace_impact",
    "arguments": {"ticker": "TSMC", "max_hops": 2},
    "agent_id": "cli"
  }'
```

### Chat Endpoint

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"message": "Which companies depend on TSMC?"}'
```

## Example Use Cases

- Semiconductor shock propagation:
  Query the downstream impact of a disruption at TSMC.
- Commodity-driven scenario analysis:
  Evaluate oil supply disruption effects across exposed sectors.
- Event-to-market mapping:
  Ingest a geopolitical headline and compute cascade exposure.
- Balanced thesis generation:
  Run bull/bear/judge analysis for a market event question.

## License

MIT. See `LICENSE`.

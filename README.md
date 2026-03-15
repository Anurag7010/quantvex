# Finance MCP

A real-time financial data platform built around the [Model Context Protocol (MCP)]. It exposes market data tools that any MCP-compatible LLM agent can call, and ships with a React frontend that provides both a direct quote search interface and a conversational AI chat mode powered by Google Gemini.

## Features

- **MCP Protocol Server**: Standardised tool invocation (`/invoke`) with streaming subscriptions for any MCP-compatible client.
- **Real-Time Market Data**: Live stock and crypto quotes via Alpha Vantage, Finnhub, and Binance WebSocket.
- **AI Chat Mode**: Natural-language interface backed by Gemini function calling — the model decides which MCP tools to call.
- **Search Mode**: Direct symbol lookup with 5-second auto-refresh and intraday range visualisation.
- **Two-Tier Cache**: Redis hot cache (TTL-based) and Qdrant semantic vector cache for near-instant repeat queries.
- **Data Lineage**: Neo4j graph tracks every API call, instrument, and agent interaction for full provenance.
- **News Impact Analysis**: NewsAPI → NER keyword extraction → NebulaGraph knowledge graph for supply-chain event tracing.

## Architecture

```
Browser / LLM Agent
             │
             ▼
React Frontend (TypeScript)        ← Search & Chat UI
             │
             ▼
MCP Server  (FastAPI / Python 3.11)
    ├─ /invoke          ← tool dispatch (quote.latest, quote.stream, trace_impact, analyze_news_impact)
    ├─ /subscribe       ← SSE streaming subscription
    ├─ /chat            ← Gemini agent endpoint
    │
    ├─ Connectors       ← Alpha Vantage · Finnhub · Binance WebSocket
    ├─ Redis            ← hot quote cache
    ├─ Qdrant           ← semantic query cache (all-MiniLM-L6-v2)
    ├─ Neo4j            ← data lineage graph
    └─ NebulaGraph      ← news event & supply-chain knowledge graph
```

## Project Structure

```
finance-mcp/
├── mcp_server/             # FastAPI application — routing, auth, lifespan
│   ├── invoke_handlers/    # One module per MCP tool
│   └── utils/              # Validation, logging helpers
├── connectors/             # Alpha Vantage, Finnhub, Binance integrations
├── cache/                  # Redis and Qdrant client wrappers
├── graph/                  # Neo4j lineage writer and client
├── src/finance_mcp/        # NebulaGraph client, news ingestion pipeline
├── frontend/               # React 19 + TypeScript SPA
├── infra/                  # Primary Docker Compose (Redis/Qdrant/Neo4j/MCP)
├── docker/                 # NebulaGraph cluster Docker Compose
├── examples/               # Standalone Gemini CLI agent
├── scripts/                # Seed, verification, and pipeline scripts
└── tests/                  # Pytest test suite
```

## Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Node.js 18+ (frontend only)
- API keys from:
  - [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
  - [Finnhub](https://finnhub.io/register)
  - [NewsAPI](https://newsapi.org/register) (optional — news analysis tool)
  - [Google AI Studio](https://aistudio.google.com/) (optional — Gemini chat mode)

## Installation

### 1. Clone and configure environment

```bash
git clone https://github.com/Anurag7010/finance-mcp.git
cd finance-mcp
cp infra/.env.example .env
```

Open `.env` and fill in your API keys. All available variables with descriptions are documented in `infra/.env.example`.

### 2. Start core infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

This starts Redis, Qdrant, Neo4j, and the MCP server on their default ports. The MCP API is available at `http://localhost:8000`.

### 3. Start the NebulaGraph cluster

Required only for the `trace_impact` and `analyze_news_impact` tools.

```bash
docker compose -f docker/nebula-docker-compose.yml up -d
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm start
```

The app opens at `http://localhost:3000`.

## Usage

### Search mode

Type any stock or crypto symbol (`AAPL`, `TSLA`, `BTCUSDT`) into the search bar. Toggle **Live** to enable 5-second auto-refresh. Recent queries are persisted in local storage.

### AI Agent mode

Switch to **Agent** in the top navigation. Ask questions in plain English:

> "What is the current price of Apple?"  
> "Compare Bitcoin and Ethereum performance today."  
> "Trace the supply-chain impact of the latest TSMC news."

The Gemini model uses function calling to dispatch MCP tools automatically.

### CLI agent

```bash
python examples/gemini_agent.py
```

Runs the same Gemini-backed agent in an interactive terminal session.

### Calling the MCP server directly

```bash
curl -X POST http://localhost:8000/invoke \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $MCP_API_KEY" \
    -d '{"tool": "quote.latest", "parameters": {"symbol": "AAPL"}}'
```

See `mcp_server/capabilities.json` for the full tool schema.

## MCP Tools

| Tool                  | Description                                                  |
| --------------------- | ------------------------------------------------------------ |
| `quote.latest`        | Latest bid/ask/price for a stock or crypto symbol            |
| `quote.stream`        | Subscribe to a streaming price feed via SSE                  |
| `trace_impact`        | Trace financial impact across the Neo4j lineage graph        |
| `analyze_news_impact` | Extract events from recent news and map supply-chain effects |

## Security

- All write and data endpoints (`/invoke`, `/subscribe`, `/chat`) require an `X-API-Key` header matching `MCP_API_KEY`.
- API keys for third-party services are read from environment variables at startup; they are never embedded in source code or exposed to frontend clients.
- See `infra/.env.example` for the complete list of required secrets.

## Development

Run the backend outside Docker for faster iteration:

```bash
export PYTHONPATH="$PWD:$PWD/src"
pip install -r requirements.txt
uvicorn mcp_server.server:app --reload --port 8000
```

Run the test suite:

```bash
pytest tests/
```

Utility scripts for seeding data and verifying the pipeline are in `scripts/`. See `scripts/README.md` for details.

## License

MIT — see [LICENSE](LICENSE) for details.

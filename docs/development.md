# QuantVex — Running the Stack

## 1. Start services

```bash
# Redis (native, already installed via Homebrew)
brew services start redis

# Qdrant + Memgraph via Colima
colima start --memory 4 --cpu 2 --disk 20
docker context use colima
docker rm -f finance-mcp-memgraph 2>/dev/null; docker compose -f docker/memgraph-docker-compose.yml up -d memgraph && docker compose -f infra/docker-compose.yml up -d qdrant
```

## 2. Seed graph (first time only)

```bash
source .venv/bin/activate
PYTHONPATH=src python scripts/seed_production_data.py
```

## 3. Start MCP server

```bash
source .venv/bin/activate
MEMGRAPH_HOST=localhost PYTHONPATH=src uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000 --reload
```

## 4. Start frontend

```bash
cd frontend && npm start
```

---

## Stop

```bash
docker compose -f infra/docker-compose.yml -f docker/memgraph-docker-compose.yml down
colima stop
brew services stop redis
```

---

## Service URLs

| Service   | URL                             |
| --------- | ------------------------------- |
| MCP API   | http://localhost:8000/health    |
| Frontend  | http://localhost:3000           |
| Qdrant UI | http://localhost:6333/dashboard |

Should I buy or sell AAPL right now?  
Analyze NVDA supply chain risk  
Which companies are exposed if TSMC has a supply disruption?

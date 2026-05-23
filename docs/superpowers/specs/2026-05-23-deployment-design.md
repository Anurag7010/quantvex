# QuantVex Deployment Design

**Date:** 2026-05-23  
**Status:** Approved  
**Goal:** Deploy QuantVex as a live, publicly accessible application at zero cost using free-tier managed services, suitable as a top-tier portfolio project.

---

## 1. Architecture

```
GitHub (main branch)
       │
       ├── push → Vercel          →  quantvex.vercel.app        (React 19 SPA)
       │                                      │ HTTPS
       └── push → Railway         →  quantvex-api.up.railway.app (FastAPI)
                                              │
                        ┌─────────────────────┼───────────────────────┐
                        │                     │                       │
                   Upstash Redis         Neo4j AuraDB           External APIs
                   (quote cache)         (supply chain          (Finnhub, AV,
                                          graph)                 OpenAI, News)
```

### Service Allocation

| Service | Platform | Free Tier Limits |
|---|---|---|
| Frontend | Vercel | Unlimited static deploys, CDN |
| Backend | Railway | $5 credit/month (~500 hrs always-on) |
| Redis | Upstash | 10K cmds/day, 256 MB, TLS |
| Graph DB | Neo4j AuraDB Free | 200K nodes/rels, Bolt compatible |
| Qdrant | Removed | Replaced by hash cache |

### Live URLs

| URL | Purpose |
|---|---|
| `https://quantvex.vercel.app` | Full frontend app |
| `https://quantvex-api.up.railway.app/health` | Health check |
| `https://quantvex-api.up.railway.app/docs` | Swagger API explorer |
| `https://quantvex-api.up.railway.app/.well-known/mcp` | MCP capability manifest |

---

## 2. Code Changes

### 2a. Dependencies (`requirements.txt`)

Remove the following packages to reduce container size from ~3 GB to ~300 MB:
- `torch==2.2.0`
- `sentence-transformers==2.7.0`
- `transformers==4.40.0`
- `langchain==0.1.20`
- `langchain-core==0.1.52`
- `qdrant-client==1.7.0`

All other dependencies remain unchanged.

### 2b. Semantic Cache Replacement (`cache/qdrant_client.py`)

Replace the Qdrant + sentence-transformers semantic cache with a SHA-256 hash-based Redis cache. The public interface (`get(query)`, `set(query, result, ttl)`) stays identical so no callers need to change. Fuzzy-match is dropped; exact-match caching remains fully functional.

### 2c. Neo4j AuraDB Fixes (`src/finance_mcp/graph/client.py` + `mcp_server/config.py`)

Two changes needed:

**Connection URI scheme** — `GraphClient.__init__` currently builds `bolt://{host}:{port}`. AuraDB requires TLS and uses `neo4j+s://` URI format. Add a `NEO4J_URI` env var to `config.py` and update `GraphClient.__init__` to use it when set:

```python
# config.py — add field
neo4j_uri: str = Field(default="", env="NEO4J_URI")

# client.py — prefer full URI over host+port construction
if neo4j_uri:
    self._uri = neo4j_uri          # e.g. neo4j+s://<id>.databases.neo4j.io
else:
    self._uri = f"bolt://{host}:{port}"   # local Memgraph fallback
```

**Index syntax** — Memgraph uses legacy index syntax; AuraDB uses standard Cypher:

```cypher
-- Before (Memgraph)
CREATE INDEX ON :Company(ticker);

-- After (Neo4j AuraDB)
CREATE INDEX company_ticker IF NOT EXISTS FOR (c:Company) ON (c.ticker);
```

Approximately 3-4 index statements need updating. All `MERGE`, `MATCH`, `WHERE`, and relationship queries are identical between both engines.

### 2d. Frontend API URL (`frontend/src/services/api.ts`)

Ensure the Axios base URL reads from the environment variable:

```typescript
const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
```

Set `REACT_APP_API_URL=https://quantvex-api.up.railway.app` in the Vercel dashboard.

---

## 3. Environment Variables

### Railway (backend)

```
OPENAI_API_KEY=<your-key>
FINNHUB_API_KEY=<your-key>
ALPHA_VANTAGE_API_KEY=<your-key>
NEWSDATA_API_KEY=<your-key>
MCP_API_KEY=<strong-random-secret>
REDIS_HOST=<upstash-endpoint>
REDIS_PORT=6380
REDIS_PASSWORD=<upstash-password>
REDIS_SSL=true
NEO4J_URI=neo4j+s://<aura-id>.databases.neo4j.io
MEMGRAPH_USER=neo4j
MEMGRAPH_PASSWORD=<aura-password>
ALLOWED_ORIGINS=https://quantvex.vercel.app
VERDICT_DB_PATH=/app/verdicts.db
```

### Vercel (frontend)

```
REACT_APP_API_URL=https://quantvex-api.up.railway.app
```

---

## 4. CI/CD

### Auto-deploy
- **Railway**: watches `main` branch → rebuilds and redeploys backend on every push (~2 min)
- **Vercel**: watches `main` branch → rebuilds and redeploys frontend on every push (~1 min)

### GitHub Actions (test gate)

File: `.github/workflows/ci.yml`  
Trigger: pull requests to `main`  
Steps: install deps → `pytest tests/ -v -m "not integration"`  
Effect: blocks merge on test failure; does not run on direct push to main.

---

## 5. One-Time Setup Sequence

1. Create **Neo4j AuraDB Free** instance at `console.neo4j.io` → copy URI + password
2. Create **Upstash Redis** free DB at `console.upstash.com` → copy host + password
3. Connect **Railway** to GitHub repo → set all env vars from Section 3 → first deploy
4. Run seed script against AuraDB: `PYTHONPATH=src python scripts/seed_production_data.py`
5. Connect **Vercel** to GitHub repo → set `REACT_APP_API_URL` → first deploy
6. Verify end-to-end at `https://quantvex.vercel.app`

---

## 6. Production Hardening

- `MCP_API_KEY` set to a cryptographically random secret (not the dev default)
- `ALLOWED_ORIGINS` locked to `https://quantvex.vercel.app` only
- Railway health check configured to hit `/health` — auto-restarts on failure
- Upstash Redis uses TLS by default (`REDIS_SSL=true`, port 6380)
- All secrets managed via platform dashboards — never committed to git

---

## 7. Portfolio Presentation

**README additions:**
- Live demo badge pointing to `https://quantvex.vercel.app`
- Architecture diagram (from the IEEE paper)
- Tech stack table listing all services and tiers
- Link to Swagger UI at `/docs`

**Swagger UI** at `https://quantvex-api.up.railway.app/docs` serves as a live, interactive API explorer — a strong portfolio signal showing a production-grade API.

---

## 8. Out of Scope

- Custom domain (free subdomains chosen)
- Staging environment
- Sentry / error monitoring
- Qdrant (semantic cache replaced by hash cache)
- Memgraph (replaced by Neo4j AuraDB)

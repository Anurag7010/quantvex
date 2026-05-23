#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── 1. Ensure Colima (Docker runtime) is running ──────────────────────────
if ! colima status 2>/dev/null | grep -q "Running"; then
  echo "▶ Starting Colima..."
  colima start --memory 4 --cpu 2 --disk 20
else
  echo "✓ Colima already running"
fi
docker context use colima >/dev/null 2>&1 || true

# ── 2. Ensure native Redis is running (Homebrew) ──────────────────────────
echo "▶ Ensuring Redis is running (native)..."
brew services start redis >/dev/null 2>&1 || true
redis-cli ping >/dev/null 2>&1 && echo "✓ Redis ready" || echo "⚠ Redis not responding"

# ── 3. Start Qdrant + Memgraph in Colima ──────────────────────────────────
echo "▶ Starting Qdrant and Memgraph..."
docker rm -f finance-mcp-memgraph 2>/dev/null || true
docker compose -f "$ROOT/docker/memgraph-docker-compose.yml" up -d memgraph
docker compose -f "$ROOT/infra/docker-compose.yml" up -d qdrant

# ── 4. Wait for Qdrant and Memgraph to be healthy ─────────────────────────
echo "▶ Waiting for services to be healthy..."
for i in $(seq 1 30); do
  qdrant=$(docker inspect --format='{{.State.Health.Status}}' finance-mcp-qdrant 2>/dev/null || echo "unknown")
  mg=$(nc -z localhost 7687 2>/dev/null && echo "open" || echo "closed")
  printf "  [%02d] qdrant=%-8s memgraph=%s\r" "$i" "$qdrant" "$mg"
  if [ "$qdrant" = "healthy" ] && [ "$mg" = "open" ]; then
    echo -e "\n✓ All services healthy"
    break
  fi
  sleep 5
done

# ── 4. Start MCP server ────────────────────────────────────────────────────
echo "▶ Starting MCP server on :8000..."
source "$ROOT/.venv/bin/activate"
MEMGRAPH_HOST=localhost PYTHONPATH=src uvicorn mcp_server.server:app \
  --host 0.0.0.0 --port 8000 --reload

# QuantVex Scripts

Operational scripts for the QuantVex stack. These are not pytest tests — they require running infrastructure (Memgraph/Neo4j AuraDB, Redis, or live API keys) and are meant to be executed manually to seed data, run end-to-end smoke tests, or verify a deployed environment.

## Scripts

| Script | Purpose |
|--------|---------|
| `seed_production_data.py` | Seeds 57 companies, 20 commodities, 100+ edges into Memgraph via Bolt (local/Docker) |
| `seed_via_http.py` | Seeds the same data into Neo4j AuraDB via HTTP REST (cloud deployments without direct Bolt access) |
| `verify_system.py` | Checks all service connections (Memgraph, Redis, Qdrant), handler registration, and pipeline health |
| `e2e_pipeline.py` | Full end-to-end smoke test: NewsClient → EventParser → EventIngestor → Memgraph → trace_impact |

## Usage

```bash
# Seed the supply-chain graph (local Memgraph via Bolt)
PYTHONPATH=src python scripts/seed_production_data.py

# Seed via HTTP (cloud/AuraDB — no direct Bolt required)
PYTHONPATH=src python scripts/seed_via_http.py

# Verify all system components are healthy
PYTHONPATH=src:. python scripts/verify_system.py

# Run the full e2e pipeline validation
PYTHONPATH=src:. python scripts/e2e_pipeline.py
```

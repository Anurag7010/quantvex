"""
Operational scripts for the finance-mcp stack.

These are not pytest tests — they require running infrastructure
(NebulaGraph, Neo4j, Redis, or live API keys) and are meant to be
executed manually to seed data, run end-to-end smoke tests, or
verify a deployed environment.

## Usage examples

# Seed the supply-chain graph with production data

PYTHONPATH=src NEBULA_HOST=localhost .venv/bin/python scripts/seed_production_data.py

# Run the full e2e pipeline validation

PYTHONPATH=src:. .venv/bin/python scripts/e2e_pipeline.py

# Verify all system components are healthy

PYTHONPATH=src:. .venv/bin/python scripts/verify_system.py
"""

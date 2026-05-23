# QuantVex Free-Tier Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy QuantVex to free-tier managed services (Vercel + Railway + Upstash Redis + Neo4j AuraDB) with zero cost, full live functionality, and a public URL suitable for a portfolio.

**Architecture:** Frontend (React 19) deploys to Vercel; backend (FastAPI) deploys to Railway using a lean Docker container (~300 MB instead of the current ~3 GB). The Qdrant + sentence-transformers semantic cache is replaced by an identical-interface hash-based Redis cache. Memgraph is replaced by Neo4j AuraDB (free, Bolt-compatible) via a one-line URI override in GraphClient.

**Tech Stack:** Vercel (frontend CDN), Railway (backend container), Upstash Redis (TLS, free tier), Neo4j AuraDB Free (graph DB), Groq (free LLM API, OpenAI-SDK-compatible), GitHub Actions (CI gate on PRs).

---

## File Map

| File | Action | What changes |
|---|---|---|
| `mcp_server/config.py` | Modify | Add `groq_api_key`, `redis_password`, `redis_ssl`, `neo4j_uri` fields |
| `mcp_server/chat_agent.py` | Modify | Use Groq base URL + `llama-3.3-70b-versatile` model |
| `src/finance_mcp/edgar/supplier_extractor.py` | Modify | Use Groq base URL + `llama-3.3-70b-versatile` model |
| `requirements.txt` | Modify | Remove torch, sentence-transformers, transformers, langchain, langchain-core, qdrant-client |
| `cache/redis_client.py` | Modify | Pass `password` and `ssl` kwargs to `redis.Redis()` |
| `cache/qdrant_client.py` | Rewrite | Replace with hash-based Redis cache, same public interface |
| `tests/test_semantic_cache.py` | Create | Unit tests for the new hash cache (mocked Redis) |
| `src/finance_mcp/graph/client.py` | Modify | Read `NEO4J_URI` env var; use it when set instead of `bolt://` |
| `.github/workflows/ci.yml` | Create | Run unit tests on every PR to main |
| `frontend/.env.example` | Modify | Add `REACT_APP_API_URL` and `REACT_APP_API_KEY` |
| `README.md` | Modify | Add live demo badge, update cache description |

---

## Task 0: Migrate from OpenAI GPT-4o to Groq (free tier)

**Files:**
- Modify: `mcp_server/config.py`
- Modify: `mcp_server/chat_agent.py`
- Modify: `src/finance_mcp/edgar/supplier_extractor.py`

**Why Groq:** Groq provides a free API tier (no credit card) with an OpenAI-SDK-compatible endpoint. Model `llama-3.3-70b-versatile` supports function/tool calling and JSON mode — the two features QuantVex depends on. The `openai` Python package is reused unchanged; only the `base_url` and model name change.

**Get your free API key:** Sign up at [console.groq.com](https://console.groq.com), create an API key — it's instant and free.

- [ ] **Step 1: Add `groq_api_key` field to config.py**

In `mcp_server/config.py`, after the `openai_model: str = "gpt-4o"` line, add:

```python
    groq_api_key: str = Field(default="", env="GROQ_API_KEY")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", env="GROQ_BASE_URL")
    groq_model: str = Field(default="llama-3.3-70b-versatile", env="GROQ_MODEL")
```

- [ ] **Step 2: Write a test for the new config fields**

Append to `tests/test_config_fields.py` (create it if it doesn't exist yet):

```python
def test_groq_api_key_defaults_empty():
    from mcp_server.config import Settings
    s = Settings()
    assert s.groq_api_key == ""

def test_groq_model_default():
    from mcp_server.config import Settings
    s = Settings()
    assert s.groq_model == "llama-3.3-70b-versatile"

def test_groq_api_key_reads_from_env():
    import os
    from mcp_server.config import Settings
    from unittest.mock import patch
    with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test123"}):
        s = Settings()
        assert s.groq_api_key == "gsk_test123"
```

Run:

```bash
source .venv/bin/activate && PYTHONPATH=. pytest tests/test_config_fields.py -v
```

Expected: all tests PASS (the new ones confirm the fields exist and are readable).

- [ ] **Step 3: Update chat_agent.py to use Groq**

In `mcp_server/chat_agent.py`, find the `__init__` method (around lines 74–82). Replace:

```python
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o"
        self.conversation_history: list[dict[str, Any]] = []
        self._tools = self._build_tools()
        self._system_prompt = self._build_system_prompt()
```

With:

```python
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY not configured")

        self.client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
        self.model = settings.groq_model
        self.conversation_history: list[dict[str, Any]] = []
        self._tools = self._build_tools()
        self._system_prompt = self._build_system_prompt()
```

- [ ] **Step 4: Update supplier_extractor.py to use Groq**

In `src/finance_mcp/edgar/supplier_extractor.py`, find the function that creates the OpenAI client (around lines 75–88). Replace:

```python
    settings = get_settings()
    if not settings.openai_api_key:
        logger.warning("edgar_extractor: OPENAI_API_KEY not set — returning empty relationships")
        return []

    client = AsyncOpenAI(api_key=settings.openai_api_key)
```

With:

```python
    settings = get_settings()
    if not settings.groq_api_key:
        logger.warning("edgar_extractor: GROQ_API_KEY not set — returning empty relationships")
        return []

    client = AsyncOpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
    )
```

And replace the model name on the `client.chat.completions.create(...)` call:

```python
            model=settings.groq_model,
```

(was `model="gpt-4o"`)

- [ ] **Step 5: Update server.py health check for the new key name**

In `mcp_server/server.py`, find this block (around line 448):

```python
    status_payload["components"]["openai"] = {
        "status": "ok" if settings.openai_api_key else "misconfigured"
    }
    if not settings.openai_api_key:
        status_payload["status"] = "degraded"
```

Replace with:

```python
    status_payload["components"]["openai"] = {
        "status": "ok" if settings.groq_api_key else "misconfigured"
    }
    if not settings.groq_api_key:
        status_payload["status"] = "degraded"
```

- [ ] **Step 6: Run unit tests to confirm nothing is broken**

```bash
source .venv/bin/activate && PYTHONPATH=.:src pytest tests/ -v -m "not integration"
```

Expected: all non-integration tests PASS.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/config.py mcp_server/chat_agent.py \
        src/finance_mcp/edgar/supplier_extractor.py \
        mcp_server/server.py tests/test_config_fields.py
git commit -m "feat: migrate from OpenAI GPT-4o to Groq free-tier API"
```

---

## Task 1: Strip heavy ML dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Remove the six packages from requirements.txt**

Open `requirements.txt` and delete these lines entirely:

```
sentence-transformers==2.7.0
torch==2.2.0
transformers==4.40.0
langchain==0.1.20
langchain-core==0.1.52
qdrant-client==1.7.0
```

The file should still contain all other packages (fastapi, uvicorn, redis, neo4j, openai, etc.).

- [ ] **Step 2: Verify the file looks correct**

Run:
```bash
grep -E "torch|sentence|transformers|langchain|qdrant" requirements.txt
```

Expected: no output (all six packages are gone).

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: strip heavy ML deps for lean container deploy"
```

---

## Task 2: Extend config with Redis SSL and Neo4j URI fields

**Files:**
- Modify: `mcp_server/config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_fields.py`:

```python
import os
import pytest
from unittest.mock import patch


def test_redis_ssl_defaults_false():
    from mcp_server.config import Settings
    s = Settings()
    assert s.redis_ssl is False


def test_redis_password_defaults_empty():
    from mcp_server.config import Settings
    s = Settings()
    assert s.redis_password == ""


def test_neo4j_uri_defaults_empty():
    from mcp_server.config import Settings
    s = Settings()
    assert s.neo4j_uri == ""


def test_redis_ssl_reads_from_env():
    from mcp_server.config import Settings
    with patch.dict(os.environ, {"REDIS_SSL": "true"}):
        s = Settings()
        assert s.redis_ssl is True


def test_neo4j_uri_reads_from_env():
    from mcp_server.config import Settings
    with patch.dict(os.environ, {"NEO4J_URI": "neo4j+s://abc123.databases.neo4j.io"}):
        s = Settings()
        assert s.neo4j_uri == "neo4j+s://abc123.databases.neo4j.io"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && PYTHONPATH=. pytest tests/test_config_fields.py -v
```

Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'redis_ssl'`

- [ ] **Step 3: Add the three fields to config.py**

In `mcp_server/config.py`, after the existing `redis_db: int = 0` line, add:

```python
    redis_password: str = Field(default="", env="REDIS_PASSWORD")
    redis_ssl: bool = Field(default=False, env="REDIS_SSL")
```

And after the existing `openai_model: str = "gpt-4o"` line, add:

```python
    neo4j_uri: str = Field(default="", env="NEO4J_URI")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && PYTHONPATH=. pytest tests/test_config_fields.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/config.py tests/test_config_fields.py
git commit -m "feat: add redis_password, redis_ssl, neo4j_uri config fields"
```

---

## Task 3: Add Redis SSL/password support to RedisClient

**Files:**
- Modify: `cache/redis_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_fields.py` (append to existing file):

```python
def test_redis_client_passes_password_and_ssl(monkeypatch):
    import redis as redis_lib
    from unittest.mock import patch, MagicMock
    mock_redis_cls = MagicMock()
    mock_instance = MagicMock()
    mock_redis_cls.return_value = mock_instance

    with patch("cache.redis_client.redis.Redis", mock_redis_cls):
        with patch.dict(os.environ, {"REDIS_PASSWORD": "secret", "REDIS_SSL": "true", "REDIS_PORT": "6380"}):
            from mcp_server.config import Settings
            import importlib
            import cache.redis_client as rc
            # Force re-init with new env
            with patch.object(rc, "_redis_client", None):
                with patch("cache.redis_client.get_settings", return_value=Settings()):
                    client = rc.RedisClient()
                    mock_redis_cls.assert_called_once()
                    kwargs = mock_redis_cls.call_args[1]
                    assert kwargs.get("password") == "secret"
                    assert kwargs.get("ssl") is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && PYTHONPATH=. pytest tests/test_config_fields.py::test_redis_client_passes_password_and_ssl -v
```

Expected: FAIL — `redis.Redis` is called without `password` or `ssl`.

- [ ] **Step 3: Update RedisClient.__init__ in cache/redis_client.py**

Replace the `self._client = redis.Redis(...)` block inside `RedisClient.__init__` (lines 26–30) with:

```python
        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            ssl=settings.redis_ssl,
            db=settings.redis_db,
            decode_responses=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && PYTHONPATH=. pytest tests/test_config_fields.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cache/redis_client.py tests/test_config_fields.py
git commit -m "feat: add Redis password and SSL support for Upstash"
```

---

## Task 4: Replace Qdrant semantic cache with hash-based Redis cache

**Files:**
- Rewrite: `cache/qdrant_client.py`
- Create: `tests/test_semantic_cache.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_semantic_cache.py`:

```python
"""Unit tests for the hash-based semantic cache (cache/qdrant_client.py)."""
import json
from unittest.mock import MagicMock
import pytest


def _make_client(mock_redis):
    from cache.qdrant_client import SemanticCacheClient
    client = SemanticCacheClient()
    client._redis = mock_redis
    return client


def test_cache_key_is_deterministic():
    from cache.qdrant_client import _cache_key
    k1 = _cache_key("AAPL", "what is the price of apple?")
    k2 = _cache_key("AAPL", "what is the price of apple?")
    assert k1 == k2
    assert k1.startswith("sem:AAPL:")


def test_cache_key_differs_by_symbol():
    from cache.qdrant_client import _cache_key
    k1 = _cache_key("AAPL", "price query")
    k2 = _cache_key("MSFT", "price query")
    assert k1 != k2


def test_search_similar_miss():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    client = _make_client(mock_redis)
    result = client.search_similar("what is aapl price", symbol="AAPL")
    assert result is None


def test_search_similar_hit():
    payload = {
        "response_text": '{"price": 195.0}',
        "symbol": "AAPL",
        "agent_id": "test",
        "timestamp": 0.0,
        "score": 1.0,
    }
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(payload)
    client = _make_client(mock_redis)
    result = client.search_similar("aapl price", symbol="AAPL")
    assert result is not None
    assert result["symbol"] == "AAPL"
    assert result["score"] == 1.0


def test_store_response_sets_correct_key_and_ttl():
    mock_redis = MagicMock()
    client = _make_client(mock_redis)
    ok = client.store_response(
        agent_id="agent1",
        symbol="AAPL",
        query_text="what is aapl price",
        response_text='{"price": 195.0}',
    )
    assert ok is True
    mock_redis.setex.assert_called_once()
    key, ttl, raw = mock_redis.setex.call_args[0]
    assert key.startswith("sem:AAPL:")
    assert ttl > 0
    stored = json.loads(raw)
    assert stored["symbol"] == "AAPL"
    assert stored["response_text"] == '{"price": 195.0}'


def test_search_similar_no_symbol_returns_none():
    mock_redis = MagicMock()
    client = _make_client(mock_redis)
    result = client.search_similar("some query", symbol=None)
    assert result is None
    mock_redis.get.assert_not_called()


def test_initialize_success():
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    client = _make_client(mock_redis)
    assert client.initialize() is True


def test_initialize_failure():
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("connection refused")
    client = _make_client(mock_redis)
    assert client.initialize() is False


def test_health_failure():
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("connection refused")
    client = _make_client(mock_redis)
    assert client.health() is False


def test_get_semantic_cache_is_singleton():
    from cache import qdrant_client as qc
    qc._semantic_cache = None
    c1 = qc.get_semantic_cache()
    c2 = qc.get_semantic_cache()
    assert c1 is c2
    qc._semantic_cache = None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && PYTHONPATH=. pytest tests/test_semantic_cache.py -v
```

Expected: FAIL — current `cache/qdrant_client.py` imports `qdrant_client` and `sentence_transformers` which are not installed.

- [ ] **Step 3: Rewrite cache/qdrant_client.py**

Replace the entire contents of `cache/qdrant_client.py` with:

```python
"""
Hash-based semantic cache backed by Redis.

Replaces the former Qdrant + sentence-transformers implementation.
Public interface is identical so all callers (server.py, quote_latest.py) require no changes.
"""
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp_server.config import get_settings
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)

_CACHE_PREFIX = "sem:"


def _cache_key(symbol: str, query_text: str) -> str:
    digest = hashlib.sha256(query_text.encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}{symbol.upper()}:{digest}"


class SemanticCacheClient:
    """Redis-backed query cache using SHA-256 hash keys.

    Drop-in replacement for the former Qdrant + sentence-transformers client.
    Exact-match caching only (no fuzzy similarity); TTL enforces the recency window.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._recency_seconds = settings.semantic_cache_recency_minutes * 60
        self._redis: Optional[Any] = None

    def _get_redis(self) -> Any:
        if self._redis is None:
            import redis as redis_lib
            settings = get_settings()
            self._redis = redis_lib.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                ssl=settings.redis_ssl,
                db=settings.redis_db,
                decode_responses=True,
            )
        return self._redis

    def initialize(self) -> bool:
        try:
            self._get_redis().ping()
            logger.info("semantic_cache_initialized")
            return True
        except Exception as e:
            logger.warning("semantic_cache_init_failed", error=str(e))
            return False

    def health(self) -> bool:
        try:
            self._get_redis().ping()
            return True
        except Exception as e:
            logger.error("semantic_cache_health_error", error=str(e))
            return False

    def search_similar(
        self,
        query_text: str,
        symbol: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 1,
    ) -> Optional[Dict[str, Any]]:
        if not symbol:
            return None
        key = _cache_key(symbol, query_text)
        try:
            raw = self._get_redis().get(key)
            if raw is None:
                logger.debug("semantic_cache_miss", query=query_text[:50])
                return None
            payload = json.loads(raw)
            logger.info("semantic_cache_hit", symbol=symbol, query=query_text[:50])
            return payload
        except Exception as e:
            logger.error("semantic_search_error", error=str(e))
            return None

    def store_response(
        self,
        agent_id: str,
        symbol: str,
        query_text: str,
        response_text: str,
    ) -> bool:
        key = _cache_key(symbol, query_text)
        payload = json.dumps({
            "response_text": response_text,
            "symbol": symbol.upper(),
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().timestamp(),
            "score": 1.0,
        })
        try:
            self._get_redis().setex(key, self._recency_seconds, payload)
            logger.info("semantic_cache_stored", symbol=symbol, query=query_text[:50])
            return True
        except Exception as e:
            logger.error("semantic_store_error", error=str(e))
            return False

    def get_collection_stats(self) -> Dict[str, Any]:
        try:
            count = len(self._get_redis().keys(f"{_CACHE_PREFIX}*"))
            return {"cached_entries": count}
        except Exception as e:
            logger.error("collection_stats_error", error=str(e))
            return {}


_semantic_cache: Optional[SemanticCacheClient] = None


def get_semantic_cache() -> SemanticCacheClient:
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCacheClient()
    return _semantic_cache
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && PYTHONPATH=. pytest tests/test_semantic_cache.py -v
```

Expected: 10 tests PASS.

- [ ] **Step 5: Run the full unit test suite to confirm nothing broke**

```bash
source .venv/bin/activate && PYTHONPATH=.:src pytest tests/ -v -m "not integration"
```

Expected: all non-integration tests PASS.

- [ ] **Step 6: Commit**

```bash
git add cache/qdrant_client.py tests/test_semantic_cache.py
git commit -m "feat: replace Qdrant semantic cache with hash-based Redis cache"
```

---

## Task 5: Update GraphClient to use NEO4J_URI for AuraDB

**Files:**
- Modify: `src/finance_mcp/graph/client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_client_uri.py`:

```python
"""Unit tests for GraphClient URI override via NEO4J_URI env var."""
import os
from unittest.mock import patch, MagicMock
import pytest


def test_graph_client_uses_bolt_by_default():
    from finance_mcp.graph.client import GraphClient
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("NEO4J_URI", None)
        client = GraphClient(host="localhost", port=7687)
        assert client._uri == "bolt://localhost:7687"


def test_graph_client_uses_neo4j_uri_when_set():
    from finance_mcp.graph.client import GraphClient
    aura_uri = "neo4j+s://abc123.databases.neo4j.io"
    with patch.dict(os.environ, {"NEO4J_URI": aura_uri}):
        client = GraphClient(host="localhost", port=7687)
        assert client._uri == aura_uri


def test_graph_client_ignores_host_port_when_uri_set():
    from finance_mcp.graph.client import GraphClient
    aura_uri = "neo4j+s://abc123.databases.neo4j.io"
    with patch.dict(os.environ, {"NEO4J_URI": aura_uri}):
        client = GraphClient(host="should-be-ignored", port=9999)
        assert "should-be-ignored" not in client._uri
        assert client._uri == aura_uri
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && PYTHONPATH=src pytest tests/test_graph_client_uri.py -v
```

Expected: `test_graph_client_uses_neo4j_uri_when_set` and `test_graph_client_ignores_host_port_when_uri_set` FAIL — currently `GraphClient.__init__` always builds `bolt://{host}:{port}`.

- [ ] **Step 3: Update GraphClient.__init__ in src/finance_mcp/graph/client.py**

Find the `__init__` method (around line 106). Replace:

```python
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        user: str = AGENT_USER,
        password: str = AGENT_PASSWORD,
    ) -> None:
        self._uri = f"bolt://{host}:{port}"
        self._user = user
        self._password = password
        self._driver: Optional[Driver] = None
```

With:

```python
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        user: str = AGENT_USER,
        password: str = AGENT_PASSWORD,
    ) -> None:
        neo4j_uri = os.environ.get("NEO4J_URI", "")
        self._uri = neo4j_uri if neo4j_uri else f"bolt://{host}:{port}"
        self._user = user
        self._password = password
        self._driver: Optional[Driver] = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && PYTHONPATH=src pytest tests/test_graph_client_uri.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finance_mcp/graph/client.py tests/test_graph_client_uri.py
git commit -m "feat: support NEO4J_URI env var for Neo4j AuraDB connection"
```

---

## Task 6: Add GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflows directory and file**

```bash
mkdir -p .github/workflows
```

Create `.github/workflows/ci.yml` with this content:

```yaml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run unit tests
        run: pytest tests/ -v -m "not integration"
        env:
          OPENAI_API_KEY: "test-key-not-used-in-unit-tests"
          MCP_API_KEY: "test-key"
          FINNHUB_API_KEY: "demo"
          ALPHA_VANTAGE_API_KEY: "demo"
          PYTHONPATH: ".:src"
```

- [ ] **Step 2: Verify the YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions unit test gate on PRs to main"
```

---

## Task 7: Update frontend .env.example and README

**Files:**
- Modify: `frontend/.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update frontend/.env.example**

Replace the entire contents of `frontend/.env.example` with:

```
# Backend API URL — set to Railway URL in production
REACT_APP_API_URL=http://localhost:8000

# API key — must match MCP_API_KEY on the backend
REACT_APP_API_KEY=dev_key_change_in_production
```

- [ ] **Step 2: Add live demo badge to README.md**

In `README.md`, find the existing badges block (the lines with `[![Python]`, `[![FastAPI]`, etc., just before the closing `</div>`). Add this badge as the first item in the badges list, before the Python badge:

```markdown
[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen?style=flat-square)](https://quantvex.vercel.app)
```

- [ ] **Step 3: Update the cache description in README.md**

Find this line in the README:
```
- Two-level cache: Redis snapshot + Qdrant semantic cache
```

Replace it with:
```
- Two-level cache: Redis snapshot + hash-based semantic cache
```

- [ ] **Step 4: Add deployment section to README**

Find the `---` that comes after the Key Features section (before `## Architecture` or similar heading) and add this block before it:

```markdown
## Live Demo

| Service | URL |
|---|---|
| Frontend | [quantvex.vercel.app](https://quantvex.vercel.app) |
| API (Swagger) | [quantvex-api.up.railway.app/docs](https://quantvex-api.up.railway.app/docs) |
| MCP Manifest | [quantvex-api.up.railway.app/.well-known/mcp](https://quantvex-api.up.railway.app/.well-known/mcp) |

```

- [ ] **Step 5: Commit**

```bash
git add frontend/.env.example README.md
git commit -m "docs: add live demo URLs and update cache description in README"
```

---

## Task 8: Merge to main and verify Railway + Vercel build

- [ ] **Step 1: Ensure all unit tests pass on the current branch**

```bash
source .venv/bin/activate && PYTHONPATH=.:src pytest tests/ -v -m "not integration"
```

Expected: all tests PASS. Fix any failures before continuing.

- [ ] **Step 2: Push branch and open PR to main**

```bash
git push origin v2/final
```

Then open a PR from `v2/final` → `main` on GitHub. The CI workflow you added in Task 6 will run automatically. Wait for the green check.

- [ ] **Step 3: Merge the PR**

Merge via GitHub UI once CI is green.

- [ ] **Step 4: Connect Railway to the repo**

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo → select `Anurag7010/finance-mcp`
2. Set the root directory to `/` and the start command to: `uvicorn mcp_server.server:app --host 0.0.0.0 --port $PORT`
3. Add all environment variables from the spec (`OPENAI_API_KEY`, `FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `NEWSDATA_API_KEY`, `MCP_API_KEY`, `REDIS_HOST`, `REDIS_PORT=6380`, `REDIS_PASSWORD`, `REDIS_SSL=true`, `NEO4J_URI`, `MEMGRAPH_USER=neo4j`, `MEMGRAPH_PASSWORD`, `ALLOWED_ORIGINS=https://quantvex.vercel.app`)
4. Railway will auto-deploy from `main`. Watch the build log — it should complete in ~3 minutes with the lean requirements.

- [ ] **Step 5: Connect Vercel to the repo**

1. Go to [vercel.com](https://vercel.com) → New Project → Import `Anurag7010/finance-mcp`
2. Set Framework Preset to **Create React App**, Root Directory to `frontend`
3. Add environment variable: `REACT_APP_API_URL=https://quantvex-api.up.railway.app` and `REACT_APP_API_KEY=<your-mcp-api-key>`
4. Deploy. The build takes ~1 minute.

- [ ] **Step 6: Create Neo4j AuraDB free instance and seed the graph**

1. Go to [console.neo4j.io](https://console.neo4j.io) → Create Free Instance → copy the connection URI and password
2. Set `NEO4J_URI` on Railway to the AuraDB URI (format: `neo4j+s://<id>.databases.neo4j.io`)
3. Set `MEMGRAPH_PASSWORD` to the AuraDB password and `MEMGRAPH_USER=neo4j`
4. Seed the graph locally against AuraDB:

```bash
source .venv/bin/activate
NEO4J_URI=neo4j+s://<your-id>.databases.neo4j.io \
MEMGRAPH_USER=neo4j \
MEMGRAPH_PASSWORD=<your-aura-password> \
PYTHONPATH=src python scripts/seed_production_data.py
```

Expected: script completes without errors, seeding 57 companies, 20 commodities, and 100+ edges.

- [ ] **Step 7: Create Upstash Redis free DB**

1. Go to [console.upstash.com](https://console.upstash.com) → Create Database → select free tier → enable TLS
2. Copy the endpoint, port (6380), and password
3. Set `REDIS_HOST`, `REDIS_PORT=6380`, `REDIS_PASSWORD`, `REDIS_SSL=true` in Railway env vars
4. Railway will redeploy automatically.

- [ ] **Step 8: Smoke test the live deployment**

```bash
# Replace with your actual Railway URL and API key
curl -s -H "X-API-Key: <your-mcp-api-key>" \
  https://quantvex-api.up.railway.app/health | python3 -m json.tool
```

Expected: `{"status": "ok", ...}` with all components showing `"ok"` or at worst `"degraded"` only for optional services.

```bash
curl -s https://quantvex-api.up.railway.app/.well-known/mcp | python3 -m json.tool
```

Expected: JSON capability manifest with all 7 tools listed.

Then open `https://quantvex.vercel.app` in a browser, log in, and run a chat query (e.g., "What is the current price of AAPL?") to confirm the full end-to-end path works.

- [ ] **Step 9: Final commit — update README with confirmed live URLs**

After both deployments are confirmed live, update the Live Demo table in `README.md` with the actual verified URLs and commit to `main`:

```bash
git add README.md
git commit -m "docs: confirm live deployment URLs in README"
git push origin main
```

---

## Self-Check Against Spec

| Spec requirement | Task that implements it |
|---|---|
| Replace paid OpenAI with free Groq API | Task 0 |
| Remove torch/sentence-transformers/qdrant-client | Task 1 |
| Add redis_password + redis_ssl to config | Task 2 |
| Redis client uses password + SSL | Task 3 |
| Hash-based semantic cache, same interface | Task 4 |
| NEO4J_URI override in GraphClient | Task 5 |
| GitHub Actions CI gate | Task 6 |
| Frontend REACT_APP_API_URL env var | Task 7 |
| Live demo badge in README | Task 7 |
| Railway + Vercel + AuraDB + Upstash wiring | Task 8 |
| Seed script run against AuraDB | Task 8 |
| Smoke test end-to-end | Task 8 |

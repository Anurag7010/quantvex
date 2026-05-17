
import json
import time
import ssl
from collections import defaultdict
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import aiohttp
try:
    import certifi
except Exception:  # pragma: no cover
    certifi = None
from fastapi import FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from mcp_server.config import get_settings
from mcp_server.utils.logging import setup_logging, get_logger
from mcp_server.schemas import ToolInvocation, ToolResponse, SubscriptionRequest
from mcp_server.invoke_handlers import (
    handle_quote_latest,
    handle_quote_stream,
    handle_unsubscribe,
    get_active_subscriptions,
    handle_trace_impact,
    handle_news_analysis,
    handle_multi_agent_analysis,
)
from cache.redis_client import get_redis_client
from cache.qdrant_client import get_semantic_cache
from finance_mcp.graph.client import SecureGraphClient

try:
    from mcp_server.chat_agent import get_chat_agent
    GPT_AVAILABLE = True
except Exception:
    GPT_AVAILABLE = False

# Setup logging
setup_logging()
logger = get_logger(__name__)


def _build_ssl_context() -> ssl.SSLContext:
    if certifi is None:
        logger.warning("ssl_certifi_missing")
        return ssl.create_default_context()
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except Exception as exc:
        logger.warning("ssl_certifi_failed", error=str(exc))
        return ssl.create_default_context()


_SSL_CONTEXT = _build_ssl_context()

# Load capabilities
CAPABILITIES_PATH = Path(__file__).parent / "capabilities.json"

# API Key Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60


def check_rate_limit(api_key: str) -> bool:
    """Return False when an API key exceeds the in-memory request limit."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    requests = [timestamp for timestamp in _rate_limits[api_key] if timestamp > window_start]
    _rate_limits[api_key] = requests
    if len(requests) >= RATE_LIMIT_REQUESTS:
        return False
    _rate_limits[api_key].append(now)
    return True


async def get_api_key(api_key: str = Security(api_key_header)):
    """Validate API key from request header"""
    settings = get_settings()
    if api_key == settings.mcp_api_key:
        if not check_rate_limit(api_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("mcp_server_starting")
    
    # Initialize Redis
    redis_client = get_redis_client()
    if redis_client.connect():
        logger.info("redis_initialized")
    else:
        logger.warning("redis_connection_failed")
    
    # Initialize Qdrant
    semantic_cache = get_semantic_cache()
    if semantic_cache.initialize():
        logger.info("qdrant_initialized")
    else:
        logger.warning("qdrant_initialization_failed")
    
    logger.info("mcp_server_started")
    
    yield
    
    # Cleanup
    logger.info("mcp_server_stopping")
    redis_client.close()


settings = get_settings()
app = FastAPI(
    title=settings.mcp_server_name,
    version=settings.mcp_server_version,
    description="Real-Time Financial Data MCP Integration System",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)


@app.options("/{path:path}")
async def options_handler(path: str, request: Request):
    """Handle CORS preflight requests."""
    origin = request.headers.get("origin", "")
    headers = {
        "Access-Control-Allow-Methods": "GET, POST",
        "Access-Control-Allow-Headers": "X-API-Key, Content-Type",
        "Access-Control-Max-Age": "86400",
    }
    if origin in settings.allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return Response(
        status_code=200,
        headers=headers,
    )


@app.get("/.well-known/mcp")
async def mcp_metadata():
    """MCP server metadata and protocol version."""
    return {
        "name": settings.mcp_server_name,
        "version": settings.mcp_server_version,
        "protocol_version": "1.0",
        "description": "Real-Time Financial Data MCP Integration System",
        "capabilities": ["tools", "subscriptions"],
        "endpoints": {
            "capabilities": "/capabilities",
            "invoke": "/invoke",
            "subscribe": "/subscribe",
            "unsubscribe": "/unsubscribe"
        }
    }


@app.get("/capabilities")
async def get_capabilities():
    """Available MCP tools and their input/output schemas."""
    try:
        with open(CAPABILITIES_PATH, "r") as f:
            capabilities = json.load(f)
        return capabilities
    except FileNotFoundError:
        logger.error("capabilities_file_not_found")
        raise HTTPException(status_code=500, detail="Capabilities file not found")
    except json.JSONDecodeError:
        logger.error("capabilities_json_error")
        raise HTTPException(status_code=500, detail="Invalid capabilities file")


@app.post("/invoke", dependencies=[Security(get_api_key)])
async def invoke_tool(request: ToolInvocation):
    """Execute an MCP tool. Requires X-API-Key header."""
    logger.info(
        "invoke_request",
        tool=request.tool_name,
        args=request.arguments
    )
    
    try:
        tool_name = request.tool_name.lower()
        args = request.arguments
        
        if tool_name == "quote.latest":
            response = await handle_quote_latest(
                symbol=args.get("symbol"),
                exchange=args.get("exchange"),
                max_age_sec=args.get("maxAgeSec"),
                agent_id=request.agent_id,
                query_text=request.query_text
            )
        
        elif tool_name == "quote.stream":
            response = await handle_quote_stream(
                symbol=args.get("symbol"),
                channel=args.get("channel", "trades"),
                agent_id=request.agent_id
            )

        elif tool_name == "trace_impact":
            response = await handle_trace_impact(
                ticker=args.get("ticker"),
                max_hops=args.get("max_hops", 2),
                agent_id=request.agent_id,
            )

        elif tool_name == "analyze_news_impact":
            response = await handle_news_analysis(
                query=args.get("query", ""),
                limit=args.get("limit", 10),
                max_hops=args.get("max_hops", 2),
                ticker=args.get("ticker") or None,
                agent_id=request.agent_id,
            )

        elif tool_name == "multi_agent_analysis":
            response = await handle_multi_agent_analysis(
                query=args.get("query", ""),
                ticker=args.get("ticker") or None,
                agent_id=request.agent_id,
            )

        else:
            response = ToolResponse(
                success=False,
                error=(
                    f"Unknown tool: {tool_name}. Available tools: quote.latest, "
                    "quote.stream, trace_impact, analyze_news_impact, multi_agent_analysis"
                )
            )
        
        if response.success:
            return JSONResponse(content=response.model_dump())
        else:
            return JSONResponse(
                status_code=400,
                content=response.model_dump()
            )
            
    except Exception as e:
        logger.error("invoke_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content=ToolResponse(
                success=False,
                error=f"Internal error: {str(e)}"
            ).model_dump()
        )


@app.post("/subscribe", dependencies=[Security(get_api_key)])
async def subscribe(request: SubscriptionRequest):
    """Subscribe to a real-time symbol stream. Requires X-API-Key header."""
    logger.info(
        "subscribe_request",
        symbol=request.symbol,
        channel=request.channel
    )
    
    try:
        response = await handle_quote_stream(
            symbol=request.symbol,
            channel=request.channel,
            agent_id=request.agent_id
        )
        
        if response.success:
            return JSONResponse(content=response.model_dump())
        else:
            return JSONResponse(
                status_code=400,
                content=response.model_dump()
            )
            
    except Exception as e:
        logger.error("subscribe_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


class UnsubscribeRequest(BaseModel):
    subscription_id: str


@app.post("/unsubscribe", dependencies=[Security(get_api_key)])
async def unsubscribe(request: UnsubscribeRequest):
    """Unsubscribe from a stream. Requires X-API-Key header."""
    logger.info("unsubscribe_request", subscription_id=request.subscription_id)
    
    try:
        response = await handle_unsubscribe(request.subscription_id)
        
        if response.success:
            return JSONResponse(content=response.model_dump())
        else:
            return JSONResponse(
                status_code=400,
                content=response.model_dump()
            )
            
    except Exception as e:
        logger.error("unsubscribe_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    success: bool
    error: Optional[str] = None


@app.post("/chat", dependencies=[Security(get_api_key)])
async def chat(request: ChatRequest):
    """Chat with the GPT AI agent. Requires X-API-Key header."""
    if not GPT_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content=ChatResponse(
                response="",
                success=False,
                error="GPT chat agent not available. Check OPENAI_API_KEY configuration."
            ).model_dump()
        )
    
    try:
        agent = get_chat_agent()
        response_text = await agent.chat(request.message)
        
        return JSONResponse(
            content=ChatResponse(
                response=response_text,
                success=True
            ).model_dump()
        )
    
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        error_msg = str(e)

        lower_error = error_msg.lower()
        if "429" in error_msg or "quota" in lower_error or "rate limit" in lower_error:
            error_msg = "The OpenAI API quota or rate limit has been exceeded. Please try again shortly or check your billing settings."
        elif "401" in error_msg or "authentication" in lower_error or "incorrect api key" in lower_error:
            error_msg = "Invalid OpenAI API key. Please check your configuration."
        elif "OPENAI_API_KEY" in error_msg:
            error_msg = "OpenAI API key not configured. Please add it to your environment settings."
        
        return JSONResponse(
            status_code=200,  # Return 200 so frontend can display error message
            content=ChatResponse(
                response="",
                success=False,
                error=error_msg
            ).model_dump()
        )


@app.get("/health")
async def health_check():
    status_payload = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.mcp_server_version,
        "components": {},
    }

    redis_client = get_redis_client()

    try:
        if redis_client.is_connected():
            status_payload["components"]["redis"] = {"status": "ok"}
        else:
            raise RuntimeError("Redis ping failed")
    except Exception as e:
        status_payload["components"]["redis"] = {"status": "degraded", "error": str(e)}
        status_payload["status"] = "degraded"

    try:
        with SecureGraphClient(host=settings.nebula_host, port=settings.nebula_port) as graph_client:
            graph_client.ping()
        status_payload["components"]["nebula_graph"] = {"status": "ok"}
    except Exception as e:
        status_payload["components"]["nebula_graph"] = {"status": "degraded", "error": str(e)}
        status_payload["status"] = "degraded"

    try:
        qdrant = get_semantic_cache()
        if qdrant.health():
            status_payload["components"]["qdrant"] = {"status": "ok"}
        else:
            raise RuntimeError("Qdrant health check failed")
    except Exception as e:
        status_payload["components"]["qdrant"] = {"status": "degraded", "error": str(e)}
        status_payload["status"] = "degraded"

    status_payload["components"]["openai"] = {
        "status": "ok" if settings.openai_api_key else "misconfigured"
    }
    if not settings.openai_api_key:
        status_payload["status"] = "degraded"

    status_payload["components"]["subscriptions"] = {
        "status": "ok",
        "count": len(get_active_subscriptions()),
    }

    http_status = 200 if status_payload["status"] == "ok" else 503
    return JSONResponse(content=status_payload, status_code=http_status)


@app.get("/subscriptions")
async def list_subscriptions():
    return {
        "subscriptions": get_active_subscriptions()
    }


CRYPTO_SYMBOLS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"}


@app.get("/market/indices")
async def get_market_indices():
    """Fetch NIFTY 50, SENSEX, and USD/INR server-side (bypasses browser CORS). Cached 5 min."""
    cache_key = "market:indices"
    redis_client = get_redis_client()
    try:
        cached = redis_client._client.get(cache_key)
        if cached:
            return JSONResponse(json.loads(cached))
    except Exception:
        pass

    result = {}
    connector = aiohttp.TCPConnector(ssl=_SSL_CONTEXT)
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10),
        connector=connector,
    ) as session:
        # NIFTY 50
        try:
            async with session.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d",
                headers={"User-Agent": "Mozilla/5.0"}
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    meta = data["chart"]["result"][0]["meta"]
                    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or meta["regularMarketPrice"]
                    change_pct = ((meta["regularMarketPrice"] - prev) / prev * 100) if prev else 0
                    result["nifty"] = {
                        "price": round(meta["regularMarketPrice"], 2),
                        "change_pct": round(change_pct, 2)
                    }
        except Exception as e:
            result["nifty"] = {"error": str(e)}

        # SENSEX
        try:
            async with session.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d",
                headers={"User-Agent": "Mozilla/5.0"}
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    meta = data["chart"]["result"][0]["meta"]
                    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or meta["regularMarketPrice"]
                    change_pct = ((meta["regularMarketPrice"] - prev) / prev * 100) if prev else 0
                    result["sensex"] = {
                        "price": round(meta["regularMarketPrice"], 2),
                        "change_pct": round(change_pct, 2)
                    }
        except Exception as e:
            result["sensex"] = {"error": str(e)}

        # USD/INR
        try:
            async with session.get("https://open.er-api.com/v6/latest/USD") as r:
                if r.status == 200:
                    data = await r.json()
                    result["usd_inr"] = round(data["rates"]["INR"], 2)
        except Exception as e:
            result["usd_inr"] = None

    result["timestamp"] = datetime.utcnow().isoformat()

    try:
        redis_client._client.set(cache_key, json.dumps(result), ex=300)
    except Exception:
        pass

    return JSONResponse(result)


@app.get("/market/crypto/{symbol}")
async def get_crypto_quote(symbol: str):
    """Fetch crypto quote from Binance (no key required). Cached 30s."""
    symbol = symbol.upper()
    if symbol not in CRYPTO_SYMBOLS:
        return JSONResponse({"error": "Unsupported crypto symbol"}, status_code=400)

    cache_key = f"crypto:{symbol}"
    redis_client = get_redis_client()
    try:
        cached = redis_client._client.get(cache_key)
        if cached:
            return JSONResponse(json.loads(cached))
    except Exception:
        pass

    pair = f"{symbol}USDT"
    connector = aiohttp.TCPConnector(ssl=_SSL_CONTEXT)
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=8),
        connector=connector,
    ) as session:
        try:
            async with session.get(
                f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}"
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    price_usd = float(data["lastPrice"])

                    # Get INR rate from cached indices or use fallback
                    inr_rate = 84.0
                    try:
                        fx_cached = redis_client._client.get("market:indices")
                        if fx_cached:
                            fx_data = json.loads(fx_cached)
                            inr_rate = fx_data.get("usd_inr") or 84.0
                    except Exception:
                        pass

                    result = {
                        "symbol": symbol,
                        "price_usd": price_usd,
                        "inr_price": round(price_usd * inr_rate, 2),
                        "change_pct": round(float(data["priceChangePercent"]), 2),
                        "volume": float(data["volume"]),
                        "high_24h": float(data["highPrice"]),
                        "low_24h": float(data["lowPrice"]),
                        "source": "Binance",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    try:
                        redis_client._client.set(cache_key, json.dumps(result), ex=30)
                    except Exception:
                        pass
                    return JSONResponse(result)
                else:
                    body = await r.text()
                    return JSONResponse({"error": f"Binance returned {r.status}: {body[:200]}"}, status_code=503)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=503)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "mcp_server.server:app",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        reload=True
    )

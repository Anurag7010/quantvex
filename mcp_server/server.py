
import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
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
)
from cache.redis_client import get_redis_client
from cache.qdrant_client import get_semantic_cache
from graph.lineage_writer import get_lineage_writer

try:
    from mcp_server.chat_agent import get_chat_agent
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Load capabilities
CAPABILITIES_PATH = Path(__file__).parent / "capabilities.json"

# API Key Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)):
    """Validate API key from request header"""
    settings = get_settings()
    if api_key == settings.mcp_api_key:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
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
    
    # Initialize Neo4j lineage
    lineage_writer = get_lineage_writer()
    if lineage_writer.initialize():
        logger.info("neo4j_initialized")
    else:
        logger.warning("neo4j_initialization_failed")
    
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
    allow_origins=["*"], 
    allow_credentials=False,  
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle CORS preflight requests."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        }
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

        else:
            response = ToolResponse(
                success=False,
                error=f"Unknown tool: {tool_name}. Available tools: quote.latest, quote.stream, trace_impact, analyze_news_impact"
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
    """Chat with the Gemini AI agent. Requires X-API-Key header."""
    if not GEMINI_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content=ChatResponse(
                response="",
                success=False,
                error="Gemini chat agent not available. Check GEMINI_API_KEY configuration."
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

        if "429" in error_msg or "quota" in error_msg.lower():
            error_msg = "The Gemini API quota has been exceeded. Please try again in a few moments or check your API billing settings."
        elif "401" in error_msg or "authentication" in error_msg.lower():
            error_msg = "Invalid Gemini API key. Please check your configuration."
        elif "GEMINI_API_KEY" in error_msg:
            error_msg = "Gemini API key not configured. Please add it to your environment settings."
        
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
    redis_client = get_redis_client()
    
    return {
        "status": "healthy",
        "redis_connected": redis_client.is_connected(),
        "active_subscriptions": len(get_active_subscriptions())
    }


@app.get("/subscriptions")
async def list_subscriptions():
    return {
        "subscriptions": get_active_subscriptions()
    }


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

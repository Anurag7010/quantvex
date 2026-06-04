"""
Unified Financial Data Schema
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    ALPHA_VANTAGE = "alpha_vantage"
    FINNHUB = "finnhub"
    BINANCE = "binance"
    REDIS_CACHE = "redis_cache"
    SEMANTIC_CACHE = "semantic_cache"


class QuoteData(BaseModel):
    """Unified quote data schema for all connectors"""
    symbol: str = Field(..., description="Ticker symbol")
    price: float = Field(..., description="Current price")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data_source: DataSource = Field(..., description="Origin of data")
    cache_hit: bool = Field(default=False)
    latency_ms: float = Field(default=0.0)
    volume: Optional[float] = Field(default=None)
    bid: Optional[float] = Field(default=None)
    ask: Optional[float] = Field(default=None)
    high: Optional[float] = Field(default=None)
    low: Optional[float] = Field(default=None)
    open: Optional[float] = Field(default=None)
    previous_close: Optional[float] = Field(default=None)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StreamTick(BaseModel):
    """Single tick from a real-time stream"""
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    trade_id: Optional[str] = None
    data_source: DataSource = DataSource.BINANCE

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ToolInvocation(BaseModel):
    """MCP Tool invocation request"""
    tool_name: str = Field(..., description="Name of the tool to invoke")
    arguments: dict = Field(default_factory=dict)
    agent_id: Optional[str] = Field(default=None)
    query_text: Optional[str] = Field(default=None)


class ToolResponse(BaseModel):
    """MCP Tool response wrapper"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    cache_hit: bool = False
    data_source: Optional[str] = None
    latency_ms: float = 0.0


class SubscriptionRequest(BaseModel):
    """Stream subscription request"""
    symbol: str
    channel: str = Field(default="trades", pattern="^(trades|quotes)$")
    agent_id: Optional[str] = None


class SubscriptionResponse(BaseModel):
    """Stream subscription response"""
    subscription_id: str
    status: str
    symbol: str
    channel: str

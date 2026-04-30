"""
Input validation utilities
"""
import re
from typing import Optional
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)


class InputValidator:
    """Validates and sanitizes input parameters"""
    
    SYMBOL_PATTERN = re.compile(r'^[A-Z0-9_.\-]{1,64}$', re.IGNORECASE)
    EXCHANGE_PATTERN = re.compile(r'^[A-Z0-9_]{1,20}$', re.IGNORECASE)
    
    VALID_TOOLS = {
        "quote.latest",
        "quote.stream",
        "trace_impact",
        "analyze_news_impact",
        "multi_agent_analysis",
    }
    VALID_CHANNELS = {"trades", "quotes"}
    VALID_COMMODITY_VIDS = {
        "CRUDE_OIL", "NATURAL_GAS", "COAL", "SEMICONDUCTOR_WAFER",
        "LITHIUM", "COBALT", "COPPER", "RARE_EARTH", "ALUMINUM", "STEEL",
        "CORN", "WHEAT", "SOYBEANS", "COFFEE", "SUGAR", "PALM_OIL",
        "SHIPPING_CONTAINERS", "SEMICONDUCTOR_CHIPS", "SILICON", "NEON_GAS",
    }
    
    @classmethod
    def validate_symbol(cls, symbol: str) -> str:
        if not symbol:
            raise ValueError("Symbol cannot be empty")
        
        symbol = symbol.strip().upper()
        
        if not cls.SYMBOL_PATTERN.match(symbol):
            raise ValueError(f"Invalid symbol format: {symbol}")
        
        logger.debug("symbol_validated", symbol=symbol)
        return symbol

    @classmethod
    def validate_symbol_or_vid(cls, value: str) -> str:
        """Validate a stock ticker or known commodity VID."""
        normalized = cls.validate_symbol(value)
        if normalized in cls.VALID_COMMODITY_VIDS:
            return normalized
        return normalized
    
    @classmethod
    def validate_exchange(cls, exchange: Optional[str]) -> Optional[str]:
        if not exchange:
            return None
        
        exchange = exchange.strip().upper()
        
        if not cls.EXCHANGE_PATTERN.match(exchange):
            raise ValueError(f"Invalid exchange format: {exchange}")
        
        return exchange
    
    @classmethod
    def validate_tool_name(cls, tool_name: str) -> str:
        if not tool_name:
            raise ValueError("Tool name cannot be empty")
        
        tool_name = tool_name.strip().lower()
        
        if tool_name not in cls.VALID_TOOLS:
            raise ValueError(f"Unknown tool: {tool_name}. Valid tools: {cls.VALID_TOOLS}")
        
        return tool_name
    
    @classmethod
    def validate_channel(cls, channel: str) -> str:
        if not channel:
            return "trades"
        
        channel = channel.strip().lower()
        
        if channel not in cls.VALID_CHANNELS:
            raise ValueError(f"Invalid channel: {channel}. Valid channels: {cls.VALID_CHANNELS}")
        
        return channel
    
    @classmethod
    def validate_max_age_sec(cls, max_age_sec: Optional[int]) -> int:
        if max_age_sec is None:
            return 60
        
        if not isinstance(max_age_sec, int) or max_age_sec < 1:
            raise ValueError("maxAgeSec must be a positive integer")
        
        if max_age_sec > 3600:
            raise ValueError("maxAgeSec cannot exceed 3600 seconds")
        
        return max_age_sec
    
    @classmethod
    def sanitize_string(cls, value: str) -> str:
        if not value:
            return ""
        
        # Remove control characters and limit length
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)
        return sanitized[:1000]

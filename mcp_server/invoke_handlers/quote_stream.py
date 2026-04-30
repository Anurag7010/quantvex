"""
Quote Stream Tool Handler
MCP tool: quote.stream
"""
import uuid
from typing import Optional
from mcp_server.utils.logging import get_logger
from mcp_server.utils.validation import InputValidator
from mcp_server.schemas import SubscriptionRequest, SubscriptionResponse, ToolResponse
from connectors.binance_ws import get_binance_connector
from graph.lineage_writer import get_lineage_writer

logger = get_logger(__name__)

# Active subscriptions registry
_active_subscriptions = {}


async def handle_quote_stream(
    symbol: str,
    channel: str = "trades",
    agent_id: Optional[str] = None
) -> ToolResponse:
    """
    Handle quote.stream tool invocation
    Subscribes to real-time stream via Binance WebSocket
    
    Returns subscription_id for tracking
    """
    try:
        # Validate inputs
        symbol = InputValidator.validate_symbol(symbol)
        channel = InputValidator.validate_channel(channel)
        
        logger.info(
            "quote_stream_request",
            symbol=symbol,
            channel=channel,
            agent_id=agent_id
        )
        
        # Get Binance connector
        binance = get_binance_connector()
        
        # Subscribe to stream
        # Map channel: "trades" -> "trade", "quotes" -> "ticker"
        ws_channel = "trade" if channel == "trades" else "ticker"
        subscription_id = await binance.subscribe(symbol, ws_channel)
        
        # Register subscription
        _active_subscriptions[subscription_id] = {
            "symbol": symbol,
            "channel": channel,
            "agent_id": agent_id
        }
        
        # Record lineage if agent provided
        if agent_id:
            lineage_writer = get_lineage_writer()
            lineage_writer.record_agent_call(
                agent_id=agent_id,
                api_name="binance",
                latency_ms=0,
                response_code=200,
                symbol=symbol,
                tool_name="quote.stream"
            )
        
        response = SubscriptionResponse(
            subscription_id=subscription_id,
            status="subscribed",
            symbol=symbol,
            channel=channel
        )
        data = response.model_dump()
        data.update(
            {
                "success": True,
                "channel": f"{ws_channel}.{symbol}",
                "message": "Subscribed successfully",
            }
        )
        
        logger.info(
            "quote_stream_subscribed",
            subscription_id=subscription_id,
            symbol=symbol
        )
        
        return ToolResponse(
            success=True,
            data=data,
            cache_hit=False,
            data_source="binance"
        )
        
    except ValueError as e:
        logger.error("quote_stream_validation_error", error=str(e))
        return ToolResponse(
            success=False,
            error=str(e)
        )
    except Exception as e:
        logger.error("quote_stream_error", error=str(e))
        return ToolResponse(
            success=False,
            error=f"Failed to subscribe: {str(e)}"
        )


async def handle_unsubscribe(subscription_id: str) -> ToolResponse:
    """
    Handle unsubscribe request
    """
    try:
        if not subscription_id:
            return ToolResponse(
                success=False,
                error="subscription_id is required"
            )
        
        # Check if subscription exists
        if subscription_id not in _active_subscriptions:
            return ToolResponse(
                success=False,
                error=f"Unknown subscription: {subscription_id}"
            )
        
        # Get Binance connector
        binance = get_binance_connector()
        
        # Unsubscribe
        success = await binance.unsubscribe(subscription_id)
        
        if success:
            # Remove from registry
            sub_info = _active_subscriptions.pop(subscription_id, {})
            
            logger.info(
                "quote_stream_unsubscribed",
                subscription_id=subscription_id,
                symbol=sub_info.get("symbol")
            )
            
            return ToolResponse(
                success=True,
                data={
                    "success": True,
                    "subscription_id": subscription_id,
                    "channel": f"{sub_info.get('channel', 'trades')}.{sub_info.get('symbol', '')}",
                    "message": "Unsubscribed successfully",
                    "status": "unsubscribed",
                }
            )
        else:
            return ToolResponse(
                success=False,
                error="Failed to unsubscribe"
            )
            
    except Exception as e:
        logger.error("unsubscribe_error", error=str(e))
        return ToolResponse(
            success=False,
            error=f"Failed to unsubscribe: {str(e)}"
        )


def get_active_subscriptions() -> dict:
    """Get all active subscriptions"""
    return dict(_active_subscriptions)

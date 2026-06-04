"""
Binance WebSocket Connector
Free real-time crypto trades streaming
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Callable, Dict, Optional, Set

import websockets

from cache.redis_client import get_redis_client
from mcp_server.config import get_settings
from mcp_server.schemas import DataSource, StreamTick
from mcp_server.utils.logging import get_logger

logger = get_logger(__name__)


class BinanceWebSocketConnector:
    """
    Binance WebSocket connector for real-time crypto trades
    Stream format: wss://stream.binance.com:9443/ws/{symbol}@trade
    """
    
    def __init__(self):
        settings = get_settings()
        self._base_url = settings.binance_ws_url
        self._connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self._subscriptions: Dict[str, str] = {}  # subscription_id -> symbol
        self._callbacks: Dict[str, Callable] = {}  # subscription_id -> callback
        self._running: Set[str] = set()
        self._tasks: Dict[str, asyncio.Task] = {}
        self._redis = get_redis_client()
    
    def _get_stream_url(self, symbol: str, channel: str = "trade") -> str:
        """Build WebSocket URL for a symbol and channel"""
        symbol_lower = symbol.lower()
        return f"{self._base_url}/{symbol_lower}@{channel}"
    
    async def subscribe(
        self,
        symbol: str,
        channel: str = "trade",
        callback: Optional[Callable] = None
    ) -> str:
        """
        Subscribe to a symbol stream
        Returns subscription ID
        """
        subscription_id = f"sub_{uuid.uuid4().hex[:8]}"
        symbol_upper = symbol.upper()
        
        try:
            url = self._get_stream_url(symbol_upper, channel)
            
            logger.info(
                "binance_subscribe",
                symbol=symbol_upper,
                channel=channel,
                subscription_id=subscription_id
            )
            
            # Store subscription info
            self._subscriptions[subscription_id] = symbol_upper
            if callback:
                self._callbacks[subscription_id] = callback
            
            # Start the WebSocket listener task
            task = asyncio.create_task(
                self._listen(subscription_id, url, symbol_upper, channel)
            )
            self._tasks[subscription_id] = task
            self._running.add(subscription_id)
            
            return subscription_id
            
        except Exception as e:
            logger.error("binance_subscribe_error", error=str(e))
            raise
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from a stream"""
        try:
            if subscription_id not in self._subscriptions:
                logger.warning("unknown_subscription", subscription_id=subscription_id)
                return False
            
            # Stop the listener
            self._running.discard(subscription_id)
            
            # Cancel the task
            if subscription_id in self._tasks:
                self._tasks[subscription_id].cancel()
                try:
                    await self._tasks[subscription_id]
                except asyncio.CancelledError:
                    pass
                del self._tasks[subscription_id]
            
            # Close WebSocket connection
            if subscription_id in self._connections:
                await self._connections[subscription_id].close()
                del self._connections[subscription_id]
            
            # Clean up
            symbol = self._subscriptions.pop(subscription_id, None)
            self._callbacks.pop(subscription_id, None)
            
            logger.info(
                "binance_unsubscribed",
                subscription_id=subscription_id,
                symbol=symbol
            )
            
            return True
            
        except Exception as e:
            logger.error("binance_unsubscribe_error", error=str(e))
            return False
    
    async def _listen(self, subscription_id: str, url: str, symbol: str, channel: str):
        """Listen to WebSocket stream and process messages"""
        reconnect_delay = 1
        max_reconnect_delay = 60
        
        while subscription_id in self._running:
            try:
                async with websockets.connect(url) as ws:
                    self._connections[subscription_id] = ws
                    reconnect_delay = 1
                    
                    logger.info(
                        "binance_connected",
                        symbol=symbol,
                        subscription_id=subscription_id
                    )
                    
                    async for message in ws:
                        if subscription_id not in self._running:
                            break
                        
                        await self._process_message(subscription_id, message, symbol)
                        
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(
                    "binance_connection_closed",
                    subscription_id=subscription_id,
                    code=e.code
                )
            except Exception as e:
                logger.error(
                    "binance_stream_error",
                    subscription_id=subscription_id,
                    error=str(e)
                )
            
            # Reconnect with exponential backoff
            if subscription_id in self._running:
                logger.info(
                    "binance_reconnecting",
                    subscription_id=subscription_id,
                    delay=reconnect_delay
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    async def _process_message(self, subscription_id: str, message: str, symbol: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            
            # Parse Binance trade message format
            # {e: "trade", E: timestamp, s: symbol, p: price, q: quantity, t: trade_id, ...}
            if data.get("e") == "trade":
                tick = StreamTick(
                    symbol=data.get("s", symbol).upper(),
                    price=float(data.get("p", 0)),
                    volume=float(data.get("q", 0)),
                    timestamp=datetime.fromtimestamp(data.get("E", 0) / 1000),
                    trade_id=str(data.get("t")),
                    data_source=DataSource.BINANCE
                )
                
                # Push to Redis stream
                self._redis.add_to_stream(tick)
                
                # Update snapshot
                from mcp_server.schemas import QuoteData
                quote = QuoteData(
                    symbol=tick.symbol,
                    price=tick.price,
                    timestamp=tick.timestamp,
                    data_source=DataSource.BINANCE,
                    volume=tick.volume
                )
                self._redis.set_snapshot(quote)
                
                # Call callback if registered
                if subscription_id in self._callbacks:
                    await self._callbacks[subscription_id](tick)
                
                logger.debug(
                    "binance_tick",
                    symbol=tick.symbol,
                    price=tick.price,
                    volume=tick.volume
                )
                
        except json.JSONDecodeError as e:
            logger.error("binance_json_error", error=str(e))
        except Exception as e:
            logger.error("binance_process_error", error=str(e))
    
    async def get_latest_price(self, symbol: str) -> Optional[StreamTick]:
        """Get the latest price from Redis stream (if available)"""
        return self._redis.get_latest_from_stream(symbol)
    
    def get_active_subscriptions(self) -> Dict[str, str]:
        """Get all active subscriptions"""
        return dict(self._subscriptions)
    
    async def close_all(self):
        """Close all active subscriptions"""
        for subscription_id in list(self._subscriptions.keys()):
            await self.unsubscribe(subscription_id)
        logger.info("binance_all_closed")


# Singleton instance
_connector: Optional[BinanceWebSocketConnector] = None


def get_binance_connector() -> BinanceWebSocketConnector:
    global _connector
    if _connector is None:
        _connector = BinanceWebSocketConnector()
    return _connector

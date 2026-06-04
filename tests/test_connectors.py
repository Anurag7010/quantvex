"""
Tests for Financial Data Connectors
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.alpha_vantage import AlphaVantageConnector
from connectors.binance_ws import BinanceWebSocketConnector
from connectors.finnhub import FinnhubConnector
from mcp_server.schemas import DataSource, QuoteData, StreamTick


class TestAlphaVantageConnector:
    """Tests for Alpha Vantage connector"""
    
    @pytest.fixture
    def connector(self):
        """Create Alpha Vantage connector"""
        return AlphaVantageConnector()
    
    @pytest.mark.asyncio
    async def test_get_quote_response_parsing(self, connector):
        """Test response normalization"""
        mock_response = {
            "Global Quote": {
                "01. symbol": "AAPL",
                "02. open": "150.00",
                "03. high": "155.00",
                "04. low": "149.00",
                "05. price": "152.50",
                "06. volume": "1000000",
                "08. previous close": "151.00"
            }
        }
        
        with patch.object(connector._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()
            
            quote = await connector.get_quote("AAPL")
        
        if quote:
            assert quote.symbol == "AAPL"
            assert quote.price == 152.50
            assert quote.data_source == DataSource.ALPHA_VANTAGE
            assert quote.volume == 1000000
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, connector):
        """Test rate limit error handling"""
        mock_response = {
            "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."
        }
        
        with patch.object(connector._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()
            
            with pytest.raises(Exception):  # Should raise RateLimitError
                await connector.get_quote("AAPL")
    
    @pytest.mark.asyncio
    async def test_empty_response(self, connector):
        """Test empty response handling"""
        mock_response = {"Global Quote": {}}
        
        with patch.object(connector._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()
            
            quote = await connector.get_quote("INVALID")
        
        assert quote is None


class TestFinnhubConnector:
    """Tests for Finnhub connector"""
    
    @pytest.fixture
    def connector(self):
        """Create Finnhub connector"""
        return FinnhubConnector()
    
    @pytest.mark.asyncio
    async def test_get_quote_response_parsing(self, connector):
        """Test response normalization"""
        mock_response = {
            "c": 152.50,  # current price
            "h": 155.00,  # high
            "l": 149.00,  # low
            "o": 150.00,  # open
            "pc": 151.00,  # previous close
            "t": 1638316800  # timestamp
        }
        
        with patch.object(connector._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            
            quote = await connector.get_quote("AAPL")
        
        if quote:
            assert quote.symbol == "AAPL"
            assert quote.price == 152.50
            assert quote.data_source == DataSource.FINNHUB
            assert quote.high == 155.00
            assert quote.low == 149.00
    
    @pytest.mark.asyncio
    async def test_zero_price_handling(self, connector):
        """Test handling of zero price (no data)"""
        mock_response = {"c": 0, "h": 0, "l": 0, "o": 0, "pc": 0}
        
        with patch.object(connector._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            
            quote = await connector.get_quote("INVALID")
        
        assert quote is None


class TestBinanceConnector:
    """Tests for Binance WebSocket connector"""
    
    @pytest.fixture
    def connector(self):
        """Create Binance connector"""
        with patch("connectors.binance_ws.get_redis_client") as mock_redis:
            mock_redis.return_value = MagicMock()
            return BinanceWebSocketConnector()
    
    def test_stream_url_generation(self, connector):
        """Test WebSocket URL generation"""
        url = connector._get_stream_url("BTCUSDT", "trade")
        assert "btcusdt@trade" in url
        assert "stream.binance.com" in url
    
    @pytest.mark.asyncio
    async def test_subscription_management(self, connector):
        """Test subscription tracking"""
        # Initially no subscriptions
        assert len(connector.get_active_subscriptions()) == 0
    
    def test_tick_normalization(self):
        """Test tick data normalization"""
        tick = StreamTick(
            symbol="BTCUSDT",
            price=50000.0,
            volume=1.5,
            timestamp=datetime.utcnow(),
            trade_id="123456",
            data_source=DataSource.BINANCE
        )
        
        assert tick.symbol == "BTCUSDT"
        assert tick.price == 50000.0
        assert tick.volume == 1.5
        assert tick.data_source == DataSource.BINANCE


class TestConnectorNormalization:
    """Tests for unified schema normalization across connectors"""
    
    def test_quote_data_schema(self):
        """Test QuoteData schema has required fields"""
        quote = QuoteData(
            symbol="TEST",
            price=100.0,
            timestamp=datetime.utcnow(),
            data_source=DataSource.FINNHUB
        )
        
        assert hasattr(quote, 'symbol')
        assert hasattr(quote, 'price')
        assert hasattr(quote, 'timestamp')
        assert hasattr(quote, 'data_source')
        assert hasattr(quote, 'cache_hit')
        assert hasattr(quote, 'latency_ms')
    
    def test_stream_tick_schema(self):
        """Test StreamTick schema has required fields"""
        tick = StreamTick(
            symbol="TEST",
            price=100.0,
            volume=10.0,
            timestamp=datetime.utcnow()
        )
        
        assert hasattr(tick, 'symbol')
        assert hasattr(tick, 'price')
        assert hasattr(tick, 'volume')
        assert hasattr(tick, 'timestamp')
        assert hasattr(tick, 'trade_id')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

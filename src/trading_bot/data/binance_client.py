"""
Binance exchange client with async support.
Handles WebSocket connections and REST API calls to Binance testnet.
"""

import asyncio
import time
import hmac
import hashlib
from typing import Dict, List, Callable, Any, Optional
from decimal import Decimal
import aiohttp
import websockets
import json

from ..core.config import config
from ..core.logging_config import get_logger
from ..models.market_data import OrderBook, Trade, Ticker, PriceLevel

logger = get_logger(__name__)


class BinanceClient:
    """
    Async client for Binance API (testnet and production).
    Handles both REST API and WebSocket connections.
    """

    def __init__(self) -> None:
        """Initialize the Binance client."""
        self.api_key = config.binance.api_key
        self.api_secret = config.binance.api_secret
        self.base_url = config.binance.active_base_url
        self.ws_url = config.binance.active_ws_url

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_connections: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {}

        logger.info(
            "binance_client_initialized",
            testnet=config.binance.testnet_enabled,
            base_url=self.base_url,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate HMAC SHA256 signature for authenticated requests.

        Args:
            params: Request parameters

        Returns:
            Hex-encoded signature
        """
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    async def get_server_time(self) -> int:
        """
        Get Binance server time.

        Returns:
            Server timestamp in milliseconds
        """
        session = await self._get_session()
        url = f"{self.base_url}/v3/time"

        async with session.get(url) as response:
            data = await response.json()
            return data["serverTime"]

    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get exchange trading rules and symbol information.

        Args:
            symbol: Optional symbol to get info for

        Returns:
            Exchange information
        """
        session = await self._get_session()
        url = f"{self.base_url}/v3/exchangeInfo"

        params = {}
        if symbol:
            params["symbol"] = symbol

        async with session.get(url, params=params) as response:
            return await response.json()

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """
        Get current order book for a symbol.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            limit: Order book depth (5, 10, 20, 50, 100, 500, 1000, 5000)

        Returns:
            OrderBook instance
        """
        session = await self._get_session()
        url = f"{self.base_url}/v3/depth"

        params = {"symbol": symbol, "limit": limit}

        async with session.get(url, params=params) as response:
            data = await response.json()

            return OrderBook(
                exchange="binance",
                symbol=symbol,
                timestamp=int(time.time() * 1000),
                bids=[[Decimal(p), Decimal(q)] for p, q in data["bids"]],
                asks=[[Decimal(p), Decimal(q)] for p, q in data["asks"]],
                last_update_id=data["lastUpdateId"],
            )

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """
        Get recent trades for a symbol.

        Args:
            symbol: Trading pair symbol
            limit: Number of trades to retrieve (max 1000)

        Returns:
            List of Trade instances
        """
        session = await self._get_session()
        url = f"{self.base_url}/v3/trades"

        params = {"symbol": symbol, "limit": limit}

        async with session.get(url, params=params) as response:
            data = await response.json()

            trades = []
            for trade_data in data:
                trades.append(
                    Trade(
                        exchange="binance",
                        symbol=symbol,
                        trade_id=str(trade_data["id"]),
                        price=Decimal(trade_data["price"]),
                        quantity=Decimal(trade_data["qty"]),
                        side="buy" if trade_data["isBuyerMaker"] else "sell",
                        timestamp=trade_data["time"],
                        is_buyer_maker=trade_data["isBuyerMaker"],
                    )
                )

            return trades

    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get 24-hour ticker for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Ticker instance
        """
        session = await self._get_session()
        url = f"{self.base_url}/v3/ticker/24hr"

        params = {"symbol": symbol}

        async with session.get(url, params=params) as response:
            data = await response.json()

            return Ticker(
                exchange="binance",
                symbol=symbol,
                timestamp=data["closeTime"],
                open_price=Decimal(data["openPrice"]),
                high_price=Decimal(data["highPrice"]),
                low_price=Decimal(data["lowPrice"]),
                close_price=Decimal(data["lastPrice"]),
                volume=Decimal(data["volume"]),
                quote_volume=Decimal(data["quoteVolume"]),
                price_change=Decimal(data["priceChange"]),
                price_change_percent=Decimal(data["priceChangePercent"]),
            )

    async def subscribe_orderbook(
        self, symbol: str, callback: Callable[[OrderBook], None]
    ) -> None:
        """
        Subscribe to order book updates via WebSocket.

        Args:
            symbol: Trading pair symbol
            callback: Async function to call with order book updates
        """
        stream_name = f"{symbol.lower()}@depth20@100ms"
        ws_url = f"{self.ws_url}/{stream_name}"

        # Store callback
        if stream_name not in self._callbacks:
            self._callbacks[stream_name] = []
        self._callbacks[stream_name].append(callback)

        # Start WebSocket connection in background
        asyncio.create_task(self._handle_orderbook_ws(ws_url, symbol, stream_name))

        logger.info("subscribed_to_orderbook", symbol=symbol, stream=stream_name)

    async def _handle_orderbook_ws(
        self, ws_url: str, symbol: str, stream_name: str
    ) -> None:
        """
        Handle WebSocket connection for order book updates.

        Args:
            ws_url: WebSocket URL
            symbol: Trading pair symbol
            stream_name: Stream identifier
        """
        while True:
            try:
                async with websockets.connect(ws_url) as websocket:
                    self._ws_connections[stream_name] = websocket
                    logger.info("websocket_connected", stream=stream_name)

                    async for message in websocket:
                        data = json.loads(message)

                        # Parse order book update
                        orderbook = OrderBook(
                            exchange="binance",
                            symbol=symbol,
                            timestamp=data["E"],
                            bids=[[Decimal(p), Decimal(q)] for p, q in data["bids"]],
                            asks=[[Decimal(p), Decimal(q)] for p, q in data["asks"]],
                            last_update_id=data["lastUpdateId"],
                        )

                        # Call all registered callbacks
                        for callback in self._callbacks.get(stream_name, []):
                            if asyncio.iscoroutinefunction(callback):
                                await callback(orderbook)
                            else:
                                callback(orderbook)

            except Exception as e:
                logger.error(
                    "websocket_error",
                    stream=stream_name,
                    error=str(e),
                    exc_info=True,
                )
                # Wait before reconnecting
                await asyncio.sleep(5)

    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        # Close WebSocket connections
        for ws in self._ws_connections.values():
            await ws.close()

        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("binance_client_closed")

    async def __aenter__(self) -> "BinanceClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

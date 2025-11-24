"""
Coinbase Advanced Trade API client with async support.
Handles REST API and WebSocket connections to Coinbase.
"""

import asyncio
import time
import hmac
import hashlib
import base64
from typing import Dict, List, Callable, Any, Optional
from decimal import Decimal
import aiohttp
import websockets
import json

from ..core.logging_config import get_logger
from ..models.market_data import OrderBook, Trade, Ticker, PriceLevel
from ..utils.rate_limiter import rate_limiters
from ..utils.symbol_mapping import SymbolMapper
from .base_exchange import ExchangeClient

logger = get_logger(__name__)


class CoinbaseClient(ExchangeClient):
    """
    Async client for Coinbase Advanced Trade API.
    Handles both REST API and WebSocket connections.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        use_sandbox: bool = True,
    ):
        """
        Initialize the Coinbase client.

        Args:
            api_key: Coinbase API key
            api_secret: Coinbase API secret
            use_sandbox: Use sandbox environment (default: True)
        """
        super().__init__("coinbase")

        self.api_key = api_key
        self.api_secret = api_secret
        self.use_sandbox = use_sandbox

        # API endpoints
        if use_sandbox:
            self.base_url = "https://api-public.sandbox.exchange.coinbase.com"
            self.ws_url = "wss://ws-feed-public.sandbox.exchange.coinbase.com"
        else:
            self.base_url = "https://api.coinbase.com/api/v3/brokerage"
            self.ws_url = "wss://advanced-trade-ws.coinbase.com"

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_connections: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {}

        logger.info(
            "coinbase_client_initialized",
            sandbox=use_sandbox,
            base_url=self.base_url,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """
        Generate signature for authenticated requests.

        Args:
            timestamp: Unix timestamp
            method: HTTP method
            path: Request path
            body: Request body

        Returns:
            Base64-encoded signature
        """
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode()

    def normalize_symbol(self, symbol: str) -> str:
        """Convert normalized symbol to Coinbase format."""
        return SymbolMapper.to_exchange_symbol(symbol, "coinbase")

    def denormalize_symbol(self, exchange_symbol: str) -> str:
        """Convert Coinbase symbol to normalized format."""
        return SymbolMapper.normalize_symbol(exchange_symbol, "coinbase")

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """
        Get current order book for a symbol.

        Args:
            symbol: Trading pair symbol (normalized format)
            limit: Order book depth

        Returns:
            OrderBook instance
        """
        await rate_limiters.acquire("coinbase")

        session = await self._get_session()
        exchange_symbol = self.normalize_symbol(symbol)
        url = f"{self.base_url}/products/{exchange_symbol}/book"

        params = {"level": 2}  # Level 2 includes top 50 bids and asks

        async with session.get(url, params=params) as response:
            data = await response.json()

            bids = []
            asks = []

            # Parse bids and asks (format: [price, size, num_orders])
            for bid_data in data.get("bids", [])[:limit]:
                bids.append(
                    PriceLevel(price=Decimal(bid_data[0]), quantity=Decimal(bid_data[1]))
                )

            for ask_data in data.get("asks", [])[:limit]:
                asks.append(
                    PriceLevel(price=Decimal(ask_data[0]), quantity=Decimal(ask_data[1]))
                )

            return OrderBook(
                exchange=self.name,
                symbol=self.denormalize_symbol(exchange_symbol),
                timestamp=int(time.time() * 1000),
                bids=bids,
                asks=asks,
            )

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """
        Get recent trades for a symbol.

        Args:
            symbol: Trading pair symbol (normalized format)
            limit: Number of trades to retrieve

        Returns:
            List of Trade instances
        """
        await rate_limiters.acquire("coinbase")

        session = await self._get_session()
        exchange_symbol = self.normalize_symbol(symbol)
        url = f"{self.base_url}/products/{exchange_symbol}/trades"

        params = {"limit": min(limit, 1000)}

        async with session.get(url, params=params) as response:
            data = await response.json()

            trades = []
            for trade_data in data.get("trades", []):
                trades.append(
                    Trade(
                        exchange=self.name,
                        symbol=self.denormalize_symbol(exchange_symbol),
                        trade_id=str(trade_data["trade_id"]),
                        price=Decimal(trade_data["price"]),
                        quantity=Decimal(trade_data["size"]),
                        side=trade_data["side"],
                        timestamp=int(
                            time.mktime(
                                time.strptime(trade_data["time"], "%Y-%m-%dT%H:%M:%S.%fZ")
                            )
                            * 1000
                        ),
                    )
                )

            return trades

    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get 24-hour ticker for a symbol.

        Args:
            symbol: Trading pair symbol (normalized format)

        Returns:
            Ticker instance
        """
        await rate_limiters.acquire("coinbase")

        session = await self._get_session()
        exchange_symbol = self.normalize_symbol(symbol)
        url = f"{self.base_url}/products/{exchange_symbol}/ticker"

        async with session.get(url) as response:
            data = await response.json()

            # Get 24h stats
            stats_url = f"{self.base_url}/products/{exchange_symbol}/stats"
            async with session.get(stats_url) as stats_response:
                stats = await stats_response.json()

                return Ticker(
                    exchange=self.name,
                    symbol=self.denormalize_symbol(exchange_symbol),
                    timestamp=int(time.time() * 1000),
                    open_price=Decimal(stats.get("open", data.get("price", "0"))),
                    high_price=Decimal(stats.get("high", data.get("price", "0"))),
                    low_price=Decimal(stats.get("low", data.get("price", "0"))),
                    close_price=Decimal(data.get("price", "0")),
                    volume=Decimal(stats.get("volume", "0")),
                    quote_volume=Decimal(stats.get("volume", "0")),
                    price_change=Decimal("0"),
                    price_change_percent=Decimal("0"),
                )

    async def subscribe_orderbook(
        self, symbol: str, callback: Callable[[OrderBook], None]
    ) -> None:
        """
        Subscribe to order book updates via WebSocket.

        Args:
            symbol: Trading pair symbol (normalized format)
            callback: Async function to call with order book updates
        """
        exchange_symbol = self.normalize_symbol(symbol)
        stream_name = f"level2:{exchange_symbol}"

        # Store callback
        if stream_name not in self._callbacks:
            self._callbacks[stream_name] = []
        self._callbacks[stream_name].append(callback)

        # Start WebSocket connection in background
        asyncio.create_task(self._handle_orderbook_ws(exchange_symbol, stream_name, callback))

        logger.info("subscribed_to_coinbase_orderbook", symbol=symbol)

    async def _handle_orderbook_ws(
        self, exchange_symbol: str, stream_name: str, callback: Callable
    ) -> None:
        """
        Handle WebSocket connection for order book updates.

        Args:
            exchange_symbol: Exchange-specific symbol
            stream_name: Stream identifier
            callback: Callback function
        """
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    # Subscribe to level2 channel
                    subscribe_msg = {
                        "type": "subscribe",
                        "product_ids": [exchange_symbol],
                        "channels": ["level2"],
                    }
                    await websocket.send(json.dumps(subscribe_msg))

                    logger.info("coinbase_websocket_connected", symbol=exchange_symbol)

                    # Maintain orderbook state
                    bids_dict: Dict[str, str] = {}
                    asks_dict: Dict[str, str] = {}

                    async for message in websocket:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "snapshot":
                            # Initial snapshot
                            bids_dict = {bid[0]: bid[1] for bid in data.get("bids", [])}
                            asks_dict = {ask[0]: ask[1] for ask in data.get("asks", [])}

                            # Create orderbook
                            await self._send_orderbook_update(
                                exchange_symbol, bids_dict, asks_dict, callback
                            )

                        elif msg_type == "l2update":
                            # Incremental update
                            for change in data.get("changes", []):
                                side, price, size = change
                                if side == "buy":
                                    if Decimal(size) == 0:
                                        bids_dict.pop(price, None)
                                    else:
                                        bids_dict[price] = size
                                else:
                                    if Decimal(size) == 0:
                                        asks_dict.pop(price, None)
                                    else:
                                        asks_dict[price] = size

                            # Send updated orderbook
                            await self._send_orderbook_update(
                                exchange_symbol, bids_dict, asks_dict, callback
                            )

            except Exception as e:
                logger.error(
                    "coinbase_websocket_error",
                    symbol=exchange_symbol,
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(5)

    async def _send_orderbook_update(
        self,
        exchange_symbol: str,
        bids_dict: Dict[str, str],
        asks_dict: Dict[str, str],
        callback: Callable,
    ) -> None:
        """Send orderbook update to callback."""
        # Sort and convert to PriceLevel
        bids = sorted(
            [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty in bids_dict.items()
            ],
            key=lambda x: x.price,
            reverse=True,
        )[:50]

        asks = sorted(
            [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty in asks_dict.items()
            ],
            key=lambda x: x.price,
        )[:50]

        orderbook = OrderBook(
            exchange=self.name,
            symbol=self.denormalize_symbol(exchange_symbol),
            timestamp=int(time.time() * 1000),
            bids=bids,
            asks=asks,
        )

        if asyncio.iscoroutinefunction(callback):
            await callback(orderbook)
        else:
            callback(orderbook)

    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        self._running = False

        # Close WebSocket connections
        for ws in self._ws_connections.values():
            await ws.close()

        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("coinbase_client_closed")

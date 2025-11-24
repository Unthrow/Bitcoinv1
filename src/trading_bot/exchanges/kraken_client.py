"""
Kraken REST API and WebSocket client with async support.
Handles connections to Kraken exchange.
"""

import asyncio
import time
import hmac
import hashlib
import base64
import urllib.parse
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


class KrakenClient(ExchangeClient):
    """
    Async client for Kraken API.
    Handles both REST API and WebSocket connections.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
    ):
        """
        Initialize the Kraken client.

        Args:
            api_key: Kraken API key
            api_secret: Kraken API secret
        """
        super().__init__("kraken")

        self.api_key = api_key
        self.api_secret = api_secret

        # API endpoints
        self.base_url = "https://api.kraken.com"
        self.ws_url = "wss://ws.kraken.com"

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_connections: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {}

        # Kraken uses internal pair names that differ from REST API names
        self._pair_mappings: Dict[str, str] = {}

        logger.info("kraken_client_initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def normalize_symbol(self, symbol: str) -> str:
        """Convert normalized symbol to Kraken format."""
        return SymbolMapper.to_exchange_symbol(symbol, "kraken")

    def denormalize_symbol(self, exchange_symbol: str) -> str:
        """Convert Kraken symbol to normalized format."""
        return SymbolMapper.normalize_symbol(exchange_symbol, "kraken")

    async def _get_asset_pairs(self) -> Dict[str, str]:
        """Get Kraken asset pair information for symbol mapping."""
        if self._pair_mappings:
            return self._pair_mappings

        await rate_limiters.acquire("kraken")

        session = await self._get_session()
        url = f"{self.base_url}/0/public/AssetPairs"

        async with session.get(url) as response:
            data = await response.json()

            if data.get("error"):
                logger.error("kraken_asset_pairs_error", errors=data["error"])
                return {}

            # Map altnames to wsnames
            for pair, info in data.get("result", {}).items():
                altname = info.get("altname")
                wsname = info.get("wsname")
                if altname and wsname:
                    self._pair_mappings[altname] = wsname

            return self._pair_mappings

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """
        Get current order book for a symbol.

        Args:
            symbol: Trading pair symbol (normalized format)
            limit: Order book depth

        Returns:
            OrderBook instance
        """
        await rate_limiters.acquire("kraken")

        session = await self._get_session()
        exchange_symbol = self.normalize_symbol(symbol)
        url = f"{self.base_url}/0/public/Depth"

        params = {"pair": exchange_symbol, "count": limit}

        async with session.get(url, params=params) as response:
            data = await response.json()

            if data.get("error"):
                logger.error("kraken_orderbook_error", errors=data["error"])
                raise Exception(f"Kraken API error: {data['error']}")

            # Kraken returns data with the pair name as key
            result = data.get("result", {})
            pair_data = next(iter(result.values()), {})

            bids = []
            asks = []

            # Parse bids and asks (format: [price, volume, timestamp])
            for bid_data in pair_data.get("bids", [])[:limit]:
                bids.append(
                    PriceLevel(price=Decimal(bid_data[0]), quantity=Decimal(bid_data[1]))
                )

            for ask_data in pair_data.get("asks", [])[:limit]:
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
        await rate_limiters.acquire("kraken")

        session = await self._get_session()
        exchange_symbol = self.normalize_symbol(symbol)
        url = f"{self.base_url}/0/public/Trades"

        params = {"pair": exchange_symbol}

        async with session.get(url, params=params) as response:
            data = await response.json()

            if data.get("error"):
                logger.error("kraken_trades_error", errors=data["error"])
                return []

            result = data.get("result", {})
            pair_data = next(iter([v for k, v in result.items() if k != "last"]), [])

            trades = []
            # Format: [price, volume, time, buy/sell, market/limit, miscellaneous]
            for i, trade_data in enumerate(pair_data[:limit]):
                trades.append(
                    Trade(
                        exchange=self.name,
                        symbol=self.denormalize_symbol(exchange_symbol),
                        trade_id=str(i),
                        price=Decimal(trade_data[0]),
                        quantity=Decimal(trade_data[1]),
                        side="buy" if trade_data[3] == "b" else "sell",
                        timestamp=int(float(trade_data[2]) * 1000),
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
        await rate_limiters.acquire("kraken")

        session = await self._get_session()
        exchange_symbol = self.normalize_symbol(symbol)
        url = f"{self.base_url}/0/public/Ticker"

        params = {"pair": exchange_symbol}

        async with session.get(url, params=params) as response:
            data = await response.json()

            if data.get("error"):
                logger.error("kraken_ticker_error", errors=data["error"])
                raise Exception(f"Kraken API error: {data['error']}")

            result = data.get("result", {})
            ticker_data = next(iter(result.values()), {})

            # Kraken ticker format:
            # a = ask [price, whole lot volume, lot volume]
            # b = bid [price, whole lot volume, lot volume]
            # c = last trade closed [price, lot volume]
            # v = volume [today, last 24 hours]
            # p = volume weighted average price [today, last 24 hours]
            # t = number of trades [today, last 24 hours]
            # l = low [today, last 24 hours]
            # h = high [today, last 24 hours]
            # o = today's opening price

            return Ticker(
                exchange=self.name,
                symbol=self.denormalize_symbol(exchange_symbol),
                timestamp=int(time.time() * 1000),
                open_price=Decimal(ticker_data.get("o", "0")),
                high_price=Decimal(ticker_data.get("h", ["0"])[1]),  # 24h high
                low_price=Decimal(ticker_data.get("l", ["0"])[1]),  # 24h low
                close_price=Decimal(ticker_data.get("c", ["0"])[0]),  # Last price
                volume=Decimal(ticker_data.get("v", ["0"])[1]),  # 24h volume
                quote_volume=Decimal(ticker_data.get("v", ["0"])[1]),
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
        # Get WebSocket symbol name
        await self._get_asset_pairs()
        exchange_symbol = self.normalize_symbol(symbol)

        # Find WS name for this pair
        ws_symbol = self._pair_mappings.get(exchange_symbol.replace("USDT", "/USDT"), exchange_symbol)

        stream_name = f"book:{ws_symbol}"

        # Store callback
        if stream_name not in self._callbacks:
            self._callbacks[stream_name] = []
        self._callbacks[stream_name].append(callback)

        # Start WebSocket connection
        asyncio.create_task(self._handle_orderbook_ws(ws_symbol, stream_name, callback))

        logger.info("subscribed_to_kraken_orderbook", symbol=symbol, ws_symbol=ws_symbol)

    async def _handle_orderbook_ws(
        self, ws_symbol: str, stream_name: str, callback: Callable
    ) -> None:
        """
        Handle WebSocket connection for order book updates.

        Args:
            ws_symbol: WebSocket symbol name
            stream_name: Stream identifier
            callback: Callback function
        """
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    # Subscribe to book channel
                    subscribe_msg = {
                        "event": "subscribe",
                        "pair": [ws_symbol],
                        "subscription": {"name": "book", "depth": 25},
                    }
                    await websocket.send(json.dumps(subscribe_msg))

                    logger.info("kraken_websocket_connected", symbol=ws_symbol)

                    # Maintain orderbook state
                    bids_dict: Dict[str, str] = {}
                    asks_dict: Dict[str, str] = {}

                    async for message in websocket:
                        data = json.loads(message)

                        # Skip non-data messages
                        if isinstance(data, dict):
                            if data.get("event") == "heartbeat":
                                continue
                            elif data.get("event") in ["subscriptionStatus", "systemStatus"]:
                                logger.debug("kraken_ws_event", event=data.get("event"))
                                continue

                        if isinstance(data, list) and len(data) >= 2:
                            update = data[1]

                            # Snapshot or update
                            if "as" in update and "bs" in update:
                                # Snapshot
                                bids_dict = {bid[0]: bid[1] for bid in update.get("bs", [])}
                                asks_dict = {ask[0]: ask[1] for ask in update.get("as", [])}
                            else:
                                # Update
                                for bid in update.get("b", []):
                                    if Decimal(bid[1]) == 0:
                                        bids_dict.pop(bid[0], None)
                                    else:
                                        bids_dict[bid[0]] = bid[1]

                                for ask in update.get("a", []):
                                    if Decimal(ask[1]) == 0:
                                        asks_dict.pop(ask[0], None)
                                    else:
                                        asks_dict[ask[0]] = ask[1]

                            # Send update
                            await self._send_orderbook_update(
                                ws_symbol, bids_dict, asks_dict, callback
                            )

            except Exception as e:
                logger.error(
                    "kraken_websocket_error",
                    symbol=ws_symbol,
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(5)

    async def _send_orderbook_update(
        self,
        ws_symbol: str,
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
        )[:25]

        asks = sorted(
            [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty in asks_dict.items()
            ],
            key=lambda x: x.price,
        )[:25]

        # Convert ws symbol back to normalized
        normalized_symbol = self.denormalize_symbol(ws_symbol.replace("/", ""))

        orderbook = OrderBook(
            exchange=self.name,
            symbol=normalized_symbol,
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

        logger.info("kraken_client_closed")

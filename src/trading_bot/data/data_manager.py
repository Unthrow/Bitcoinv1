"""
DataManager: Core component for managing market data streams.
Handles connections to exchanges, data storage, and distribution.
"""

import asyncio
import json
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import asyncpg
import redis.asyncio as aioredis

from ..core.config import config
from ..core.logging_config import get_logger
from ..models.market_data import OrderBook, Trade
from .binance_client import BinanceClient

logger = get_logger(__name__)


class DataManager:
    """
    Manages market data streams from multiple exchanges.
    Handles real-time data ingestion, storage, and distribution.
    """

    def __init__(self) -> None:
        """Initialize the DataManager."""
        self.binance_client: Optional[BinanceClient] = None
        self.redis_client: Optional[aioredis.Redis] = None
        self.db_pool: Optional[asyncpg.Pool] = None

        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._orderbook_cache: Dict[str, OrderBook] = {}
        self._subscribers: Dict[str, List[Callable]] = {}

        logger.info("data_manager_initialized")

    async def start(self) -> None:
        """
        Start the DataManager and initialize all connections.
        """
        if self._running:
            logger.warning("data_manager_already_running")
            return

        logger.info("starting_data_manager")

        # Initialize connections
        await self._init_connections()

        # Start data streams
        await self._start_data_streams()

        self._running = True
        logger.info("data_manager_started")

    async def stop(self) -> None:
        """
        Stop the DataManager and cleanup all connections.
        """
        if not self._running:
            return

        logger.info("stopping_data_manager")
        self._running = False

        # Cancel all running tasks
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Close connections
        await self._close_connections()

        logger.info("data_manager_stopped")

    async def _init_connections(self) -> None:
        """Initialize connections to exchanges and databases."""
        try:
            # Initialize Binance client
            self.binance_client = BinanceClient()
            logger.info("binance_client_connected")

            # Initialize Redis
            self.redis_client = await aioredis.from_url(
                config.redis.url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self.redis_client.ping()
            logger.info("redis_connected", url=config.redis.url)

            # Initialize PostgreSQL connection pool
            self.db_pool = await asyncpg.create_pool(
                host=config.database.host,
                port=config.database.port,
                database=config.database.database,
                user=config.database.user,
                password=config.database.password,
                min_size=5,
                max_size=20,
            )
            logger.info("postgres_connected", database=config.database.database)

        except Exception as e:
            logger.error("connection_init_failed", error=str(e), exc_info=True)
            raise

    async def _close_connections(self) -> None:
        """Close all active connections."""
        if self.binance_client:
            await self.binance_client.close()

        if self.redis_client:
            await self.redis_client.close()

        if self.db_pool:
            await self.db_pool.close()

        logger.info("connections_closed")

    async def _start_data_streams(self) -> None:
        """Start real-time data streams for configured symbols."""
        if not self.binance_client:
            raise RuntimeError("Binance client not initialized")

        for symbol in config.trading.default_symbols:
            # Subscribe to order book updates
            task = asyncio.create_task(
                self._subscribe_orderbook_stream(symbol)
            )
            self._tasks.append(task)
            logger.info("orderbook_stream_started", symbol=symbol)

    async def _subscribe_orderbook_stream(self, symbol: str) -> None:
        """
        Subscribe to order book updates for a symbol.

        Args:
            symbol: Trading pair symbol
        """
        if not self.binance_client:
            return

        async def handle_orderbook_update(orderbook: OrderBook) -> None:
            """Handle incoming order book updates."""
            try:
                # Update cache
                self._orderbook_cache[symbol] = orderbook

                # Store in Redis for fast access
                await self._store_orderbook_redis(orderbook)

                # Periodically persist to PostgreSQL
                if orderbook.timestamp % 5000 < 100:  # Every ~5 seconds
                    await self._store_orderbook_postgres(orderbook)

                # Notify subscribers
                await self._notify_subscribers(f"orderbook:{symbol}", orderbook)

                logger.debug(
                    "orderbook_updated",
                    symbol=symbol,
                    best_bid=float(orderbook.best_bid.price) if orderbook.best_bid else None,
                    best_ask=float(orderbook.best_ask.price) if orderbook.best_ask else None,
                    spread=float(orderbook.spread) if orderbook.spread else None,
                )

            except Exception as e:
                logger.error(
                    "orderbook_update_failed",
                    symbol=symbol,
                    error=str(e),
                    exc_info=True,
                )

        await self.binance_client.subscribe_orderbook(symbol, handle_orderbook_update)

    async def _store_orderbook_redis(self, orderbook: OrderBook) -> None:
        """
        Store order book snapshot in Redis.

        Args:
            orderbook: OrderBook instance
        """
        if not self.redis_client:
            return

        key = f"orderbook:{orderbook.exchange}:{orderbook.symbol}"
        value = orderbook.model_dump_json()

        await self.redis_client.setex(key, 60, value)  # 60 second TTL

    async def _store_orderbook_postgres(self, orderbook: OrderBook) -> None:
        """
        Store order book snapshot in PostgreSQL.

        Args:
            orderbook: OrderBook instance
        """
        if not self.db_pool:
            return

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO orderbook_snapshots
                (exchange, symbol, timestamp, bids, asks)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (exchange, symbol, timestamp) DO NOTHING
                """,
                orderbook.exchange,
                orderbook.symbol,
                orderbook.timestamp,
                json.dumps([{"price": str(b.price), "quantity": str(b.quantity)} for b in orderbook.bids]),
                json.dumps([{"price": str(a.price), "quantity": str(a.quantity)} for a in orderbook.asks]),
            )

    async def get_orderbook(self, symbol: str) -> Optional[OrderBook]:
        """
        Get the latest order book for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest OrderBook or None if not available
        """
        # First try cache
        if symbol in self._orderbook_cache:
            return self._orderbook_cache[symbol]

        # Then try Redis
        if self.redis_client:
            key = f"orderbook:binance:{symbol}"
            data = await self.redis_client.get(key)
            if data:
                return OrderBook.model_validate_json(data)

        # Finally fetch from exchange
        if self.binance_client:
            return await self.binance_client.get_orderbook(symbol)

        return None

    def subscribe(self, channel: str, callback: Callable[[Any], None]) -> None:
        """
        Subscribe to data updates for a channel.

        Args:
            channel: Channel name (e.g., "orderbook:BTCUSDT")
            callback: Async callback function
        """
        if channel not in self._subscribers:
            self._subscribers[channel] = []

        self._subscribers[channel].append(callback)
        logger.info("subscriber_added", channel=channel)

    async def _notify_subscribers(self, channel: str, data: Any) -> None:
        """
        Notify all subscribers of a channel.

        Args:
            channel: Channel name
            data: Data to send to subscribers
        """
        for callback in self._subscribers.get(channel, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(
                    "subscriber_callback_failed",
                    channel=channel,
                    error=str(e),
                    exc_info=True,
                )

    async def get_historical_orderbooks(
        self, symbol: str, start_time: int, end_time: int, limit: int = 1000
    ) -> List[OrderBook]:
        """
        Get historical order book snapshots from PostgreSQL.

        Args:
            symbol: Trading pair symbol
            start_time: Start timestamp (milliseconds)
            end_time: End timestamp (milliseconds)
            limit: Maximum number of snapshots to return

        Returns:
            List of OrderBook instances
        """
        if not self.db_pool:
            return []

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT exchange, symbol, timestamp, bids, asks
                FROM orderbook_snapshots
                WHERE symbol = $1 AND timestamp >= $2 AND timestamp <= $3
                ORDER BY timestamp DESC
                LIMIT $4
                """,
                symbol,
                start_time,
                end_time,
                limit,
            )

            orderbooks = []
            for row in rows:
                bids_data = json.loads(row["bids"])
                asks_data = json.loads(row["asks"])

                orderbooks.append(
                    OrderBook(
                        exchange=row["exchange"],
                        symbol=row["symbol"],
                        timestamp=row["timestamp"],
                        bids=bids_data,
                        asks=asks_data,
                    )
                )

            return orderbooks

    async def __aenter__(self) -> "DataManager":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()

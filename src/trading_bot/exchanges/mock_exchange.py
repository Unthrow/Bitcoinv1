"""
Mock exchange client for testing and development.
Simulates price differences and orderbook updates.
"""

import asyncio
import random
import time
from typing import Dict, Optional, Callable, Any, List
from decimal import Decimal

from ..core.logging_config import get_logger
from ..models.market_data import OrderBook, PriceLevel

logger = get_logger(__name__)


class MockExchangeClient:
    """
    Mock exchange client that simulates orderbook updates.
    Used for testing arbitrage detection with multiple exchanges.
    """

    def __init__(
        self,
        name: str = "mock_exchange",
        price_offset_pct: float = 0.2,
        volatility: float = 0.1,
    ):
        """
        Initialize mock exchange client.

        Args:
            name: Exchange name
            price_offset_pct: Average price offset percentage from base price
            volatility: Price volatility (randomness factor)
        """
        self.name = name
        self.price_offset_pct = price_offset_pct
        self.volatility = volatility

        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._callbacks: Dict[str, List[Callable]] = {}

        # Base prices for different symbols (will be updated)
        self._base_prices: Dict[str, Decimal] = {
            "BTCUSDT": Decimal("50000"),
            "ETHUSDT": Decimal("3000"),
            "BNBUSDT": Decimal("400"),
        }

        logger.info(
            "mock_exchange_initialized",
            name=name,
            price_offset_pct=price_offset_pct,
        )

    def set_base_price(self, symbol: str, price: Decimal) -> None:
        """
        Set base price for a symbol.

        Args:
            symbol: Trading pair symbol
            price: Base price
        """
        self._base_prices[symbol] = price

    def _generate_orderbook(self, symbol: str) -> OrderBook:
        """
        Generate a mock orderbook with realistic price levels.

        Args:
            symbol: Trading pair symbol

        Returns:
            Mock OrderBook
        """
        base_price = self._base_prices.get(symbol, Decimal("1000"))

        # Apply offset and volatility
        price_multiplier = Decimal(
            1 + (self.price_offset_pct / 100) + random.uniform(-self.volatility, self.volatility) / 100
        )
        mid_price = base_price * price_multiplier

        # Generate spread
        spread_pct = Decimal(random.uniform(0.01, 0.05))  # 0.01% to 0.05%
        half_spread = mid_price * spread_pct / 2

        best_bid = mid_price - half_spread
        best_ask = mid_price + half_spread

        # Generate multiple price levels
        bids = []
        asks = []

        # Generate 10 bid levels
        for i in range(10):
            price_offset = Decimal(i) * Decimal("0.0001") * mid_price
            quantity = Decimal(random.uniform(0.1, 5.0))
            bids.append(PriceLevel(price=best_bid - price_offset, quantity=quantity))

        # Generate 10 ask levels
        for i in range(10):
            price_offset = Decimal(i) * Decimal("0.0001") * mid_price
            quantity = Decimal(random.uniform(0.1, 5.0))
            asks.append(PriceLevel(price=best_ask + price_offset, quantity=quantity))

        return OrderBook(
            exchange=self.name,
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            bids=bids,
            asks=asks,
        )

    async def subscribe_orderbook(
        self, symbol: str, callback: Callable[[OrderBook], None]
    ) -> None:
        """
        Subscribe to order book updates via simulated stream.

        Args:
            symbol: Trading pair symbol
            callback: Async function to call with order book updates
        """
        stream_name = f"{symbol.lower()}@depth"

        # Store callback
        if stream_name not in self._callbacks:
            self._callbacks[stream_name] = []
        self._callbacks[stream_name].append(callback)

        # Start simulation if not already running
        if not self._running:
            self._running = True

        # Start orderbook simulation
        task = asyncio.create_task(self._simulate_orderbook_updates(symbol, stream_name))
        self._tasks.append(task)

        logger.info("subscribed_to_mock_orderbook", symbol=symbol, exchange=self.name)

    async def _simulate_orderbook_updates(self, symbol: str, stream_name: str) -> None:
        """
        Simulate orderbook updates at regular intervals.

        Args:
            symbol: Trading pair symbol
            stream_name: Stream identifier
        """
        while self._running:
            try:
                # Generate new orderbook
                orderbook = self._generate_orderbook(symbol)

                # Call all registered callbacks
                for callback in self._callbacks.get(stream_name, []):
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(orderbook)
                        else:
                            callback(orderbook)
                    except Exception as e:
                        logger.error(
                            "mock_callback_error",
                            error=str(e),
                            exc_info=True,
                        )

                # Wait before next update (100-500ms)
                await asyncio.sleep(random.uniform(0.1, 0.5))

            except Exception as e:
                logger.error(
                    "mock_orderbook_error",
                    symbol=symbol,
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(1)

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """
        Get current mock order book for a symbol.

        Args:
            symbol: Trading pair symbol
            limit: Order book depth (ignored for mock)

        Returns:
            Mock OrderBook instance
        """
        return self._generate_orderbook(symbol)

    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        logger.info("mock_exchange_closed", name=self.name)

    async def __aenter__(self) -> "MockExchangeClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

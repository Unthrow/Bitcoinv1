"""
MultiExchangeManager: Manages data streams from multiple exchanges.
Extends DataManager to support arbitrage detection across exchanges.
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
from decimal import Decimal

from ..core.config import config
from ..core.logging_config import get_logger
from ..models.market_data import OrderBook
from .binance_client import BinanceClient
from ..exchanges.mock_exchange import MockExchangeClient
from ..strategies.arbitrage_detector import ArbitrageDetector

logger = get_logger(__name__)


class MultiExchangeManager:
    """
    Manages market data streams from multiple exchanges.
    Integrates with ArbitrageDetector for cross-exchange opportunity detection.
    """

    def __init__(
        self,
        enable_arbitrage: bool = True,
        enable_mock_exchange: bool = False,
    ):
        """
        Initialize the MultiExchangeManager.

        Args:
            enable_arbitrage: Enable arbitrage detection
            enable_mock_exchange: Enable mock exchange for testing
        """
        self.enable_arbitrage = enable_arbitrage
        self.enable_mock_exchange = enable_mock_exchange

        # Exchange clients
        self.exchanges: Dict[str, Any] = {}

        # Arbitrage detector
        self.arbitrage_detector: Optional[ArbitrageDetector] = None

        self._running = False
        self._tasks: List[asyncio.Task] = []

        logger.info(
            "multi_exchange_manager_initialized",
            enable_arbitrage=enable_arbitrage,
            enable_mock=enable_mock_exchange,
        )

    async def start(self) -> None:
        """Start the manager and initialize all connections."""
        if self._running:
            logger.warning("multi_exchange_manager_already_running")
            return

        logger.info("starting_multi_exchange_manager")

        # Initialize Binance client
        binance_client = BinanceClient()
        self.exchanges["binance"] = binance_client

        # Initialize mock exchange if enabled
        if self.enable_mock_exchange:
            mock_client = MockExchangeClient(
                name="mock_exchange",
                price_offset_pct=0.25,  # 0.25% higher prices on average
                volatility=0.15,  # Some randomness
            )
            self.exchanges["mock_exchange"] = mock_client

        # Initialize arbitrage detector
        if self.enable_arbitrage:
            from ..strategies.arbitrage_config import ArbitrageConfig

            arb_config = ArbitrageConfig(
                min_profit_percent=Decimal("0.15"),
                safety_margin=Decimal("0.05"),
            )
            self.arbitrage_detector = ArbitrageDetector(config=arb_config)
            self.arbitrage_detector.start()

        # Subscribe to orderbook streams for all symbols
        await self._subscribe_all_streams()

        self._running = True
        logger.info("multi_exchange_manager_started")

    async def _subscribe_all_streams(self) -> None:
        """Subscribe to orderbook streams for all configured symbols."""
        for symbol in config.trading.default_symbols:
            for exchange_name, client in self.exchanges.items():
                # Create callback for this exchange/symbol
                callback = self._create_orderbook_callback(exchange_name, symbol)

                # Subscribe to orderbook updates
                await client.subscribe_orderbook(symbol, callback)

                logger.info(
                    "subscribed_to_orderbook",
                    exchange=exchange_name,
                    symbol=symbol,
                )

    def _create_orderbook_callback(
        self, exchange_name: str, symbol: str
    ) -> Callable[[OrderBook], None]:
        """
        Create a callback function for orderbook updates.

        Args:
            exchange_name: Name of the exchange
            symbol: Trading pair symbol

        Returns:
            Async callback function
        """

        async def callback(orderbook: OrderBook) -> None:
            """Handle orderbook update."""
            try:
                # Update arbitrage detector
                if self.arbitrage_detector:
                    self.arbitrage_detector.update_orderbook(orderbook)

                # Log periodically (every ~5 seconds based on timestamp)
                if orderbook.timestamp % 5000 < 200:
                    logger.debug(
                        "orderbook_received",
                        exchange=exchange_name,
                        symbol=symbol,
                        best_bid=float(orderbook.best_bid.price)
                        if orderbook.best_bid
                        else None,
                        best_ask=float(orderbook.best_ask.price)
                        if orderbook.best_ask
                        else None,
                    )

            except Exception as e:
                logger.error(
                    "orderbook_callback_error",
                    exchange=exchange_name,
                    symbol=symbol,
                    error=str(e),
                    exc_info=True,
                )

        return callback

    async def stop(self) -> None:
        """Stop the manager and cleanup all connections."""
        if not self._running:
            return

        logger.info("stopping_multi_exchange_manager")
        self._running = False

        # Stop arbitrage detector
        if self.arbitrage_detector:
            self.arbitrage_detector.stop()

        # Close all exchange connections
        for exchange_name, client in self.exchanges.items():
            try:
                await client.close()
                logger.info("exchange_closed", exchange=exchange_name)
            except Exception as e:
                logger.error(
                    "exchange_close_error",
                    exchange=exchange_name,
                    error=str(e),
                    exc_info=True,
                )

        self.exchanges.clear()
        logger.info("multi_exchange_manager_stopped")

    def subscribe_to_opportunities(
        self, callback: Callable
    ) -> None:
        """
        Subscribe to arbitrage opportunity notifications.

        Args:
            callback: Async callback to receive opportunities
        """
        if self.arbitrage_detector:
            self.arbitrage_detector.subscribe(callback)
        else:
            logger.warning("arbitrage_detector_not_enabled")

    def get_statistics(self) -> Dict:
        """
        Get statistics from the arbitrage detector.

        Returns:
            Statistics dictionary
        """
        if self.arbitrage_detector:
            return self.arbitrage_detector.get_statistics()
        return {}

    def get_ranked_opportunities(self, limit: int = 10) -> List:
        """
        Get ranked arbitrage opportunities.

        Args:
            limit: Maximum number to return

        Returns:
            List of arbitrage opportunities
        """
        if self.arbitrage_detector:
            return self.arbitrage_detector.get_ranked_opportunities(limit)
        return []

    async def __aenter__(self) -> "MultiExchangeManager":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()

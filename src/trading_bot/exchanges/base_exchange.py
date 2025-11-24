"""
Base exchange client abstraction.
Defines the interface that all exchange clients must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Callable, Optional, Dict, Any
from decimal import Decimal

from ..models.market_data import OrderBook, Trade, Ticker


class ExchangeClient(ABC):
    """
    Abstract base class for exchange clients.
    All exchange implementations must inherit from this and implement the interface.
    """

    def __init__(self, name: str):
        """
        Initialize the exchange client.

        Args:
            name: Exchange name (e.g., "binance", "coinbase", "kraken")
        """
        self.name = name
        self._running = False

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """
        Get current order book for a symbol.

        Args:
            symbol: Trading pair symbol in normalized format (e.g., "BTC/USDT")
            limit: Order book depth

        Returns:
            OrderBook instance with normalized data
        """
        pass

    @abstractmethod
    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """
        Get recent trades for a symbol.

        Args:
            symbol: Trading pair symbol in normalized format
            limit: Number of trades to retrieve

        Returns:
            List of Trade instances
        """
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """
        Get 24-hour ticker for a symbol.

        Args:
            symbol: Trading pair symbol in normalized format

        Returns:
            Ticker instance
        """
        pass

    @abstractmethod
    async def subscribe_orderbook(
        self, symbol: str, callback: Callable[[OrderBook], None]
    ) -> None:
        """
        Subscribe to order book updates via WebSocket.

        Args:
            symbol: Trading pair symbol in normalized format
            callback: Async function to call with order book updates
        """
        pass

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """
        Convert normalized symbol format to exchange-specific format.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")

        Returns:
            Exchange-specific symbol (e.g., "BTCUSDT" for Binance, "BTC-USDT" for Coinbase)
        """
        pass

    @abstractmethod
    def denormalize_symbol(self, exchange_symbol: str) -> str:
        """
        Convert exchange-specific symbol to normalized format.

        Args:
            exchange_symbol: Exchange-specific symbol

        Returns:
            Normalized symbol (e.g., "BTC/USDT")
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        pass

    async def __aenter__(self) -> "ExchangeClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def is_running(self) -> bool:
        """Check if the client is running."""
        return self._running

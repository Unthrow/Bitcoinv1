"""
Symbol mapping and normalization across exchanges.
Handles different symbol formats used by various exchanges.
"""

from typing import Dict, Set
from ..core.logging_config import get_logger

logger = get_logger(__name__)


class SymbolMapper:
    """
    Maps symbols between normalized format and exchange-specific formats.

    Normalized format: "BASE/QUOTE" (e.g., "BTC/USDT")
    Exchange formats:
    - Binance: "BASEUSDT" (e.g., "BTCUSDT")
    - Coinbase: "BASE-USDT" (e.g., "BTC-USDT")
    - Kraken: "XBTUSDT" (e.g., "XBTUSDT") - Note: BTC becomes XBT
    """

    # Kraken uses different base currency codes
    KRAKEN_SYMBOL_MAP = {
        "BTC": "XBT",
        "DOGE": "XDG",
    }

    KRAKEN_REVERSE_MAP = {v: k for k, v in KRAKEN_SYMBOL_MAP.items()}

    # Common trading pairs we support
    SUPPORTED_PAIRS: Set[str] = {
        "BTC/USDT",
        "BTC/USD",
        "ETH/USDT",
        "ETH/USD",
        "BNB/USDT",
        "SOL/USDT",
        "ADA/USDT",
        "XRP/USDT",
    }

    @staticmethod
    def normalize_symbol(symbol: str, exchange: str) -> str:
        """
        Convert exchange-specific symbol to normalized format.

        Args:
            symbol: Exchange-specific symbol
            exchange: Exchange name

        Returns:
            Normalized symbol (BASE/QUOTE)
        """
        if "/" in symbol:
            # Already normalized
            return symbol

        if exchange in ["binance", "binance_testnet"]:
            # Binance format: BTCUSDT -> BTC/USDT
            # Try common quote currencies
            for quote in ["USDT", "USD", "BUSD", "BTC", "ETH"]:
                if symbol.endswith(quote):
                    base = symbol[: -len(quote)]
                    return f"{base}/{quote}"

        elif exchange == "coinbase":
            # Coinbase format: BTC-USDT -> BTC/USDT
            return symbol.replace("-", "/")

        elif exchange == "kraken":
            # Kraken format: XBTUSDT -> BTC/USDT
            # Handle Kraken's special naming
            for quote in ["USDT", "USD", "EUR"]:
                if symbol.endswith(quote):
                    base = symbol[: -len(quote)]
                    # Convert XBT to BTC, XDG to DOGE, etc.
                    base = SymbolMapper.KRAKEN_REVERSE_MAP.get(base, base)
                    return f"{base}/{quote}"

        # Fallback: return as-is
        logger.warning("symbol_normalization_failed", symbol=symbol, exchange=exchange)
        return symbol

    @staticmethod
    def to_exchange_symbol(normalized_symbol: str, exchange: str) -> str:
        """
        Convert normalized symbol to exchange-specific format.

        Args:
            normalized_symbol: Normalized symbol (BASE/QUOTE)
            exchange: Exchange name

        Returns:
            Exchange-specific symbol
        """
        if "/" not in normalized_symbol:
            # Already in exchange format or invalid
            return normalized_symbol

        base, quote = normalized_symbol.split("/")

        if exchange in ["binance", "binance_testnet"]:
            # Binance format: BTC/USDT -> BTCUSDT
            return f"{base}{quote}"

        elif exchange == "coinbase":
            # Coinbase format: BTC/USDT -> BTC-USDT (but they use BTC-USD)
            # Note: Coinbase primarily uses USD, not USDT
            if quote == "USDT":
                quote = "USD"  # Convert to Coinbase's preferred quote
            return f"{base}-{quote}"

        elif exchange == "kraken":
            # Kraken format: BTC/USDT -> XBTUSDT
            # Convert BTC to XBT, DOGE to XDG, etc.
            base = SymbolMapper.KRAKEN_SYMBOL_MAP.get(base, base)
            return f"{base}{quote}"

        elif exchange == "mock_exchange":
            # Mock uses normalized format
            return normalized_symbol

        return normalized_symbol

    @staticmethod
    def get_equivalent_pairs(normalized_symbol: str) -> Dict[str, str]:
        """
        Get equivalent symbol names for all exchanges.

        Args:
            normalized_symbol: Normalized symbol (BASE/QUOTE)

        Returns:
            Dictionary mapping exchange names to their symbol format
        """
        return {
            "binance": SymbolMapper.to_exchange_symbol(normalized_symbol, "binance"),
            "coinbase": SymbolMapper.to_exchange_symbol(normalized_symbol, "coinbase"),
            "kraken": SymbolMapper.to_exchange_symbol(normalized_symbol, "kraken"),
            "mock_exchange": normalized_symbol,
        }

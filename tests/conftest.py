"""
Pytest configuration and fixtures.
"""

import pytest


@pytest.fixture
def sample_orderbook_data() -> dict:
    """Sample order book data for testing."""
    return {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "timestamp": 1234567890,
        "bids": [["50000", "1.0"], ["49999", "2.0"], ["49998", "1.5"]],
        "asks": [["50001", "1.5"], ["50002", "2.5"], ["50003", "1.0"]],
        "last_update_id": 12345,
    }


@pytest.fixture
def sample_trade_data() -> dict:
    """Sample trade data for testing."""
    return {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "trade_id": "12345",
        "price": "50000",
        "quantity": "1.0",
        "side": "buy",
        "timestamp": 1234567890,
        "is_buyer_maker": False,
    }

"""
Tests for data models.
"""

import pytest
from decimal import Decimal

from src.trading_bot.models import OrderBook, PriceLevel, Trade, ArbitrageOpportunity


class TestPriceLevel:
    """Test PriceLevel model."""

    def test_create_price_level(self) -> None:
        """Test creating a price level."""
        level = PriceLevel(price="100.50", quantity="10.0")
        assert level.price == Decimal("100.50")
        assert level.quantity == Decimal("10.0")

    def test_price_level_from_float(self) -> None:
        """Test creating price level from float."""
        level = PriceLevel(price=100.50, quantity=10.0)
        assert level.price == Decimal("100.50")
        assert level.quantity == Decimal("10.0")


class TestOrderBook:
    """Test OrderBook model."""

    def test_create_orderbook(self) -> None:
        """Test creating an order book."""
        ob = OrderBook(
            exchange="binance",
            symbol="BTCUSDT",
            timestamp=1234567890,
            bids=[["50000", "1.0"], ["49999", "2.0"]],
            asks=[["50001", "1.5"], ["50002", "2.5"]],
        )

        assert ob.exchange == "binance"
        assert ob.symbol == "BTCUSDT"
        assert len(ob.bids) == 2
        assert len(ob.asks) == 2

    def test_best_bid_ask(self) -> None:
        """Test getting best bid and ask."""
        ob = OrderBook(
            exchange="binance",
            symbol="BTCUSDT",
            timestamp=1234567890,
            bids=[["50000", "1.0"], ["49999", "2.0"]],
            asks=[["50001", "1.5"], ["50002", "2.5"]],
        )

        assert ob.best_bid is not None
        assert ob.best_bid.price == Decimal("50000")
        assert ob.best_ask is not None
        assert ob.best_ask.price == Decimal("50001")

    def test_spread(self) -> None:
        """Test calculating spread."""
        ob = OrderBook(
            exchange="binance",
            symbol="BTCUSDT",
            timestamp=1234567890,
            bids=[["50000", "1.0"]],
            asks=[["50001", "1.5"]],
        )

        assert ob.spread == Decimal("1")

    def test_mid_price(self) -> None:
        """Test calculating mid price."""
        ob = OrderBook(
            exchange="binance",
            symbol="BTCUSDT",
            timestamp=1234567890,
            bids=[["50000", "1.0"]],
            asks=[["50002", "1.5"]],
        )

        assert ob.mid_price == Decimal("50001")


class TestTrade:
    """Test Trade model."""

    def test_create_trade(self) -> None:
        """Test creating a trade."""
        trade = Trade(
            exchange="binance",
            symbol="BTCUSDT",
            trade_id="12345",
            price="50000",
            quantity="1.0",
            side="buy",
            timestamp=1234567890,
        )

        assert trade.exchange == "binance"
        assert trade.symbol == "BTCUSDT"
        assert trade.price == Decimal("50000")
        assert trade.side == "buy"

    def test_invalid_side(self) -> None:
        """Test that invalid side raises error."""
        with pytest.raises(ValueError):
            Trade(
                exchange="binance",
                symbol="BTCUSDT",
                trade_id="12345",
                price="50000",
                quantity="1.0",
                side="invalid",
                timestamp=1234567890,
            )


class TestArbitrageOpportunity:
    """Test ArbitrageOpportunity model."""

    def test_create_opportunity(self) -> None:
        """Test creating an arbitrage opportunity."""
        opp = ArbitrageOpportunity(
            symbol="BTCUSDT",
            buy_exchange="binance",
            sell_exchange="kraken",
            buy_price="50000",
            sell_price="50200",
            profit_percent="0.4",
            timestamp=1234567890,
        )

        assert opp.symbol == "BTCUSDT"
        assert opp.profit_percent == Decimal("0.4")
        assert opp.is_profitable is True

    def test_not_profitable(self) -> None:
        """Test unprofitable opportunity."""
        opp = ArbitrageOpportunity(
            symbol="BTCUSDT",
            buy_exchange="binance",
            sell_exchange="kraken",
            buy_price="50000",
            sell_price="50100",
            profit_percent="0.2",  # Below 0.3% threshold
            timestamp=1234567890,
        )

        assert opp.is_profitable is False

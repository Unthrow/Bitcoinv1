"""
Tests for arbitrage detection system.
"""

import pytest
from decimal import Decimal
import time

from src.trading_bot.strategies import (
    ArbitrageDetector,
    ArbitrageConfig,
    ExchangeFees,
)
from src.trading_bot.models import OrderBook, PriceLevel


class TestExchangeFees:
    """Test ExchangeFees model."""

    def test_default_fees(self) -> None:
        """Test default fee structure."""
        fees = ExchangeFees()
        assert fees.maker_fee == Decimal("0.001")
        assert fees.taker_fee == Decimal("0.001")
        assert fees.withdrawal_fee == Decimal("0.0005")

    def test_total_roundtrip_fee(self) -> None:
        """Test total roundtrip fee calculation."""
        fees = ExchangeFees(
            maker_fee=Decimal("0.001"),
            taker_fee=Decimal("0.001"),
            withdrawal_fee=Decimal("0.0005"),
        )
        # Buy (taker) + Sell (taker) + Withdrawal = 0.001 + 0.001 + 0.0005
        expected = Decimal("0.0025")
        assert fees.total_roundtrip_fee == expected

    def test_custom_fees(self) -> None:
        """Test custom fee structure."""
        fees = ExchangeFees(
            maker_fee=Decimal("0.002"),
            taker_fee=Decimal("0.0025"),
            withdrawal_fee=Decimal("0.001"),
        )
        assert fees.maker_fee == Decimal("0.002")
        assert fees.taker_fee == Decimal("0.0025")


class TestArbitrageConfig:
    """Test ArbitrageConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = ArbitrageConfig()
        assert config.min_profit_percent == Decimal("0.15")
        assert config.safety_margin == Decimal("0.05")
        assert config.max_slippage_percent == Decimal("0.1")

    def test_effective_min_profit(self) -> None:
        """Test effective minimum profit calculation."""
        config = ArbitrageConfig(
            min_profit_percent=Decimal("0.15"), safety_margin=Decimal("0.05")
        )
        assert config.effective_min_profit == Decimal("0.20")

    def test_get_fees(self) -> None:
        """Test getting fees for an exchange."""
        config = ArbitrageConfig()
        binance_fees = config.get_fees("binance")
        assert binance_fees.taker_fee == Decimal("0.001")

    def test_get_fees_unknown_exchange(self) -> None:
        """Test getting fees for unknown exchange returns defaults."""
        config = ArbitrageConfig()
        unknown_fees = config.get_fees("unknown_exchange")
        assert unknown_fees.taker_fee == Decimal("0.001")


class TestArbitrageDetector:
    """Test ArbitrageDetector class."""

    def test_detector_initialization(self) -> None:
        """Test detector initialization."""
        detector = ArbitrageDetector()
        assert detector.config is not None
        assert detector.stats.total_detected == 0
        assert not detector._running

    def test_detector_with_custom_config(self) -> None:
        """Test detector with custom configuration."""
        config = ArbitrageConfig(min_profit_percent=Decimal("0.20"))
        detector = ArbitrageDetector(config=config)
        assert detector.config.min_profit_percent == Decimal("0.20")

    def test_start_stop(self) -> None:
        """Test starting and stopping detector."""
        detector = ArbitrageDetector()
        detector.start()
        assert detector._running is True

        detector.stop()
        assert detector._running is False

    def test_subscribe(self) -> None:
        """Test subscribing to opportunities."""
        detector = ArbitrageDetector()

        callback_called = []

        def callback(opp):
            callback_called.append(opp)

        detector.subscribe(callback)
        assert len(detector._opportunity_callbacks) == 1

    def test_slippage_calculation(self) -> None:
        """Test slippage calculation."""
        detector = ArbitrageDetector()

        # Create price levels with varying quantities
        price_levels = [
            PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0")),
            PriceLevel(price=Decimal("50010"), quantity=Decimal("2.0")),
            PriceLevel(price=Decimal("50020"), quantity=Decimal("1.5")),
        ]

        # Calculate slippage for quantity that spans multiple levels
        slippage = detector._calculate_orderbook_slippage(
            price_levels, Decimal("2.5"), is_buy=True
        )

        # Should have some slippage since we're consuming multiple levels
        assert slippage > Decimal("0")
        assert slippage < Decimal("0.1")  # Should be less than 0.1%

    def test_slippage_single_level(self) -> None:
        """Test slippage with sufficient liquidity at best price."""
        detector = ArbitrageDetector()

        price_levels = [
            PriceLevel(price=Decimal("50000"), quantity=Decimal("10.0")),
        ]

        # Small quantity within first level
        slippage = detector._calculate_orderbook_slippage(
            price_levels, Decimal("1.0"), is_buy=True
        )

        # Should have zero slippage
        assert slippage == Decimal("0")

    def test_update_orderbook(self) -> None:
        """Test updating orderbook in detector."""
        detector = ArbitrageDetector()
        detector.start()

        orderbook = OrderBook(
            exchange="binance",
            symbol="BTCUSDT",
            timestamp=int(time.time() * 1000),
            bids=[["50000", "1.0"]],
            asks=[["50100", "1.0"]],
        )

        # Should not raise any errors
        detector.update_orderbook(orderbook)

        # Check orderbook was stored
        key = ("binance", "BTCUSDT")
        assert key in detector._orderbooks

    @pytest.mark.asyncio
    async def test_opportunity_detection(self) -> None:
        """Test detecting arbitrage opportunity."""
        config = ArbitrageConfig(
            min_profit_percent=Decimal("0.10"),  # Lower threshold for testing
            safety_margin=Decimal("0.01"),
        )
        detector = ArbitrageDetector(config=config)
        detector.start()

        opportunities = []

        async def callback(opp):
            opportunities.append(opp)

        detector.subscribe(callback)

        # Create two orderbooks with price difference
        # Exchange 1: Lower ask price (good for buying)
        orderbook1 = OrderBook(
            exchange="exchange1",
            symbol="BTCUSDT",
            timestamp=int(time.time() * 1000),
            bids=[["49900", "5.0"]],
            asks=[["50000", "5.0"]],  # Lower ask
        )

        # Exchange 2: Higher bid price (good for selling)
        orderbook2 = OrderBook(
            exchange="exchange2",
            symbol="BTCUSDT",
            timestamp=int(time.time() * 1000),
            bids=[["50200", "5.0"]],  # Higher bid
            asks=[["50300", "5.0"]],
        )

        # Update both orderbooks
        detector.update_orderbook(orderbook1)
        detector.update_orderbook(orderbook2)

        # Wait a bit for async processing
        import asyncio

        await asyncio.sleep(0.1)

        # Should have detected opportunity
        assert detector.stats.total_detected > 0

    def test_get_ranked_opportunities(self) -> None:
        """Test getting ranked opportunities."""
        detector = ArbitrageDetector()

        # Initially empty
        ranked = detector.get_ranked_opportunities(limit=5)
        assert len(ranked) == 0

    def test_get_statistics(self) -> None:
        """Test getting statistics."""
        detector = ArbitrageDetector()
        stats = detector.get_statistics()

        assert "total_detected" in stats
        assert "total_profitable" in stats
        assert "success_rate_pct" in stats
        assert "avg_profit_pct" in stats
        assert stats["total_detected"] == 0


class TestOpportunityStats:
    """Test OpportunityStats class."""

    def test_stats_initialization(self) -> None:
        """Test stats initialization."""
        from src.trading_bot.strategies.arbitrage_detector import OpportunityStats

        stats = OpportunityStats(max_history=100)
        assert stats.total_detected == 0
        assert stats.total_profitable == 0
        assert stats.best_opportunity is None

    def test_record_opportunity(self) -> None:
        """Test recording an opportunity."""
        from src.trading_bot.strategies.arbitrage_detector import OpportunityStats
        from src.trading_bot.models import ArbitrageOpportunity

        stats = OpportunityStats()

        opp = ArbitrageOpportunity(
            symbol="BTCUSDT",
            buy_exchange="binance",
            sell_exchange="kraken",
            buy_price=Decimal("50000"),
            sell_price=Decimal("50200"),
            profit_percent=Decimal("0.35"),
            timestamp=int(time.time() * 1000),
        )

        stats.record_opportunity(opp)

        assert stats.total_detected == 1
        assert stats.total_profitable == 1  # 0.35% > 0.3% threshold
        assert stats.best_opportunity == opp

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        from src.trading_bot.strategies.arbitrage_detector import OpportunityStats
        from src.trading_bot.models import ArbitrageOpportunity

        stats = OpportunityStats()

        # Add profitable opportunity
        opp1 = ArbitrageOpportunity(
            symbol="BTCUSDT",
            buy_exchange="binance",
            sell_exchange="kraken",
            buy_price=Decimal("50000"),
            sell_price=Decimal("50200"),
            profit_percent=Decimal("0.35"),
            timestamp=int(time.time() * 1000),
        )
        stats.record_opportunity(opp1)

        # Add unprofitable opportunity
        opp2 = ArbitrageOpportunity(
            symbol="ETHUSDT",
            buy_exchange="binance",
            sell_exchange="kraken",
            buy_price=Decimal("3000"),
            sell_price=Decimal("3005"),
            profit_percent=Decimal("0.1"),  # Below threshold
            timestamp=int(time.time() * 1000),
        )
        stats.record_opportunity(opp2)

        # Success rate should be 50%
        assert stats.get_success_rate() == 50.0

    def test_avg_profit(self) -> None:
        """Test average profit calculation."""
        from src.trading_bot.strategies.arbitrage_detector import OpportunityStats
        from src.trading_bot.models import ArbitrageOpportunity

        stats = OpportunityStats()

        opp1 = ArbitrageOpportunity(
            symbol="BTCUSDT",
            buy_exchange="binance",
            sell_exchange="kraken",
            buy_price=Decimal("50000"),
            sell_price=Decimal("50200"),
            profit_percent=Decimal("0.4"),
            timestamp=int(time.time() * 1000),
        )
        stats.record_opportunity(opp1)

        opp2 = ArbitrageOpportunity(
            symbol="ETHUSDT",
            buy_exchange="binance",
            sell_exchange="kraken",
            buy_price=Decimal("3000"),
            sell_price=Decimal("3010"),
            profit_percent=Decimal("0.2"),
            timestamp=int(time.time() * 1000),
        )
        stats.record_opportunity(opp2)

        # Average should be (0.4 + 0.2) / 2 = 0.3
        avg = stats.get_avg_profit()
        assert avg == Decimal("0.3")

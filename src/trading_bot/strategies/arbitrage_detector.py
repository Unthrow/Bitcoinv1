"""
ArbitrageDetector: Detects and analyzes cross-exchange arbitrage opportunities.
"""

import asyncio
import time
from typing import List, Dict, Optional, Tuple, Callable
from decimal import Decimal
from collections import defaultdict, deque

from ..core.logging_config import get_logger
from ..models.market_data import OrderBook, ArbitrageOpportunity
from .arbitrage_config import ArbitrageConfig, ExchangeFees

logger = get_logger(__name__)


class OpportunityStats(object):
    """Statistics for tracking arbitrage opportunity performance."""

    def __init__(self, max_history: int = 1000):
        """
        Initialize opportunity statistics.

        Args:
            max_history: Maximum number of opportunities to track
        """
        self.total_detected = 0
        self.total_profitable = 0
        self.opportunities_by_pair: Dict[Tuple[str, str, str], int] = defaultdict(int)
        self.recent_opportunities: deque = deque(maxlen=max_history)
        self.best_opportunity: Optional[ArbitrageOpportunity] = None

    def record_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """Record a detected opportunity."""
        self.total_detected += 1
        if opportunity.is_profitable:
            self.total_profitable += 1

        # Track by exchange pair and symbol
        key = (opportunity.symbol, opportunity.buy_exchange, opportunity.sell_exchange)
        self.opportunities_by_pair[key] += 1

        # Keep recent opportunities
        self.recent_opportunities.append(opportunity)

        # Track best opportunity
        if (
            self.best_opportunity is None
            or opportunity.profit_percent > self.best_opportunity.profit_percent
        ):
            self.best_opportunity = opportunity

    def get_success_rate(self) -> float:
        """Get percentage of profitable opportunities."""
        if self.total_detected == 0:
            return 0.0
        return (self.total_profitable / self.total_detected) * 100

    def get_avg_profit(self) -> Decimal:
        """Get average profit percentage of recent opportunities."""
        if not self.recent_opportunities:
            return Decimal("0")

        total_profit = sum(opp.profit_percent for opp in self.recent_opportunities)
        return total_profit / len(self.recent_opportunities)


class ArbitrageDetector:
    """
    Detects cross-exchange arbitrage opportunities.

    Monitors orderbooks from multiple exchanges and identifies profitable
    price discrepancies after accounting for fees and slippage.
    """

    def __init__(self, config: Optional[ArbitrageConfig] = None):
        """
        Initialize the arbitrage detector.

        Args:
            config: Arbitrage configuration (uses defaults if not provided)
        """
        self.config = config or ArbitrageConfig()
        self.stats = OpportunityStats()

        # Storage for latest orderbooks
        self._orderbooks: Dict[Tuple[str, str], OrderBook] = {}

        # Callbacks for opportunity notifications
        self._opportunity_callbacks: List[Callable[[ArbitrageOpportunity], None]] = []

        self._running = False

        logger.info(
            "arbitrage_detector_initialized",
            min_profit=float(self.config.min_profit_percent),
            safety_margin=float(self.config.safety_margin),
        )

    def update_orderbook(self, orderbook: OrderBook) -> None:
        """
        Update orderbook data and check for arbitrage opportunities.

        Args:
            orderbook: New orderbook snapshot
        """
        key = (orderbook.exchange, orderbook.symbol)
        self._orderbooks[key] = orderbook

        # Check for opportunities with this symbol across all exchanges
        if self._running:
            asyncio.create_task(self._scan_opportunities(orderbook.symbol))

    async def _scan_opportunities(self, symbol: str) -> None:
        """
        Scan for arbitrage opportunities for a specific symbol.

        Args:
            symbol: Trading pair symbol
        """
        # Get all orderbooks for this symbol
        orderbooks = [
            ob for (exch, sym), ob in self._orderbooks.items() if sym == symbol
        ]

        if len(orderbooks) < 2:
            return  # Need at least 2 exchanges

        # Compare all pairs of exchanges
        for i, buy_ob in enumerate(orderbooks):
            for sell_ob in orderbooks[i + 1 :]:
                # Check both directions
                await self._check_arbitrage_pair(buy_ob, sell_ob)
                await self._check_arbitrage_pair(sell_ob, buy_ob)

    async def _check_arbitrage_pair(
        self, buy_orderbook: OrderBook, sell_orderbook: OrderBook
    ) -> None:
        """
        Check for arbitrage opportunity between two orderbooks.

        Args:
            buy_orderbook: Orderbook to buy from
            sell_orderbook: Orderbook to sell on
        """
        if not buy_orderbook.best_ask or not sell_orderbook.best_bid:
            return

        buy_price = buy_orderbook.best_ask.price
        buy_quantity = buy_orderbook.best_ask.quantity
        sell_price = sell_orderbook.best_bid.price
        sell_quantity = sell_orderbook.best_bid.quantity

        # Calculate gross profit percentage
        gross_profit_pct = ((sell_price - buy_price) / buy_price) * 100

        # Get fees for both exchanges
        buy_fees = self.config.get_fees(buy_orderbook.exchange)
        sell_fees = self.config.get_fees(sell_orderbook.exchange)
        total_fee_pct = (buy_fees.total_roundtrip_fee + sell_fees.taker_fee) * 100

        # Calculate net profit after fees
        net_profit_pct = gross_profit_pct - total_fee_pct

        # Calculate executable quantity (limited by both sides)
        executable_quantity = min(buy_quantity, sell_quantity)

        # Estimate slippage based on orderbook depth
        slippage_pct = self._estimate_slippage(
            buy_orderbook, sell_orderbook, executable_quantity
        )

        # Calculate final profit after slippage
        final_profit_pct = net_profit_pct - slippage_pct

        # Check if opportunity meets minimum profit threshold
        if final_profit_pct >= self.config.effective_min_profit:
            # Calculate order size in USD
            order_size_usd = float(buy_price * executable_quantity)

            # Check if order size is within limits
            if (
                order_size_usd >= float(self.config.min_order_size_usd)
                and order_size_usd <= float(self.config.max_order_size_usd)
            ):
                opportunity = ArbitrageOpportunity(
                    symbol=buy_orderbook.symbol,
                    buy_exchange=buy_orderbook.exchange,
                    sell_exchange=sell_orderbook.exchange,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    profit_percent=final_profit_pct,
                    timestamp=int(time.time() * 1000),
                    buy_quantity=executable_quantity,
                    sell_quantity=executable_quantity,
                )

                # Record stats
                self.stats.record_opportunity(opportunity)

                # Notify callbacks
                await self._notify_opportunity(opportunity)

                logger.info(
                    "arbitrage_opportunity_detected",
                    symbol=opportunity.symbol,
                    buy_exchange=opportunity.buy_exchange,
                    sell_exchange=opportunity.sell_exchange,
                    buy_price=float(buy_price),
                    sell_price=float(sell_price),
                    gross_profit_pct=float(gross_profit_pct),
                    net_profit_pct=float(net_profit_pct),
                    final_profit_pct=float(final_profit_pct),
                    quantity=float(executable_quantity),
                    order_size_usd=order_size_usd,
                    slippage_pct=float(slippage_pct),
                    fee_pct=float(total_fee_pct),
                )

    def _estimate_slippage(
        self, buy_orderbook: OrderBook, sell_orderbook: OrderBook, quantity: Decimal
    ) -> Decimal:
        """
        Estimate slippage based on orderbook depth.

        Args:
            buy_orderbook: Orderbook to buy from
            sell_orderbook: Orderbook to sell on
            quantity: Quantity to trade

        Returns:
            Estimated slippage percentage
        """
        buy_slippage = self._calculate_orderbook_slippage(
            buy_orderbook.asks, quantity, is_buy=True
        )
        sell_slippage = self._calculate_orderbook_slippage(
            sell_orderbook.bids, quantity, is_buy=False
        )

        return buy_slippage + sell_slippage

    def _calculate_orderbook_slippage(
        self, price_levels: List, quantity: Decimal, is_buy: bool
    ) -> Decimal:
        """
        Calculate slippage for a specific side of the orderbook.

        Args:
            price_levels: List of PriceLevel objects
            quantity: Quantity to execute
            is_buy: True if buying (taking asks), False if selling (taking bids)

        Returns:
            Slippage percentage
        """
        if not price_levels:
            return Decimal("0")

        best_price = price_levels[0].price
        remaining_qty = quantity
        weighted_price_sum = Decimal("0")
        total_qty = Decimal("0")

        for level in price_levels:
            if remaining_qty <= 0:
                break

            available_qty = min(level.quantity, remaining_qty)
            weighted_price_sum += level.price * available_qty
            total_qty += available_qty
            remaining_qty -= available_qty

        if total_qty == 0:
            return Decimal("0")

        avg_price = weighted_price_sum / total_qty
        slippage_pct = abs((avg_price - best_price) / best_price) * 100

        return slippage_pct

    async def _notify_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """
        Notify all registered callbacks about a new opportunity.

        Args:
            opportunity: Detected arbitrage opportunity
        """
        for callback in self._opportunity_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(opportunity)
                else:
                    callback(opportunity)
            except Exception as e:
                logger.error(
                    "opportunity_callback_failed", error=str(e), exc_info=True
                )

    def subscribe(
        self, callback: Callable[[ArbitrageOpportunity], None]
    ) -> None:
        """
        Subscribe to arbitrage opportunity notifications.

        Args:
            callback: Async callback function to receive opportunities
        """
        self._opportunity_callbacks.append(callback)
        logger.info("opportunity_subscriber_added")

    def start(self) -> None:
        """Start the arbitrage detector."""
        self._running = True
        logger.info("arbitrage_detector_started")

    def stop(self) -> None:
        """Stop the arbitrage detector."""
        self._running = False
        logger.info("arbitrage_detector_stopped")

    def get_ranked_opportunities(
        self, limit: int = 10
    ) -> List[ArbitrageOpportunity]:
        """
        Get recent opportunities ranked by profitability.

        Args:
            limit: Maximum number of opportunities to return

        Returns:
            List of opportunities sorted by profit percentage
        """
        opportunities = list(self.stats.recent_opportunities)
        opportunities.sort(key=lambda x: x.profit_percent, reverse=True)
        return opportunities[:limit]

    def get_statistics(self) -> Dict:
        """
        Get detector statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_detected": self.stats.total_detected,
            "total_profitable": self.stats.total_profitable,
            "success_rate_pct": self.stats.get_success_rate(),
            "avg_profit_pct": float(self.stats.get_avg_profit()),
            "best_opportunity": (
                {
                    "symbol": self.stats.best_opportunity.symbol,
                    "profit_pct": float(self.stats.best_opportunity.profit_percent),
                    "buy_exchange": self.stats.best_opportunity.buy_exchange,
                    "sell_exchange": self.stats.best_opportunity.sell_exchange,
                }
                if self.stats.best_opportunity
                else None
            ),
            "opportunities_by_pair": {
                f"{sym}:{buy}->{sell}": count
                for (sym, buy, sell), count in self.stats.opportunities_by_pair.items()
            },
        }

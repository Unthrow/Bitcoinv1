"""
Paper Trading Engine - Simulates trades without real money.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict

from ..core.logging_config import get_logger
from ..models.market_data import OrderBook
from ..strategies.arbitrage_config import ArbitrageConfig, ExchangeFees
from .models import (
    Balance,
    Position,
    PaperOrder,
    PaperTrade,
    OrderSide,
    OrderType,
    OrderStatus,
    PerformanceMetrics,
)

logger = get_logger(__name__)


class PaperTradingEngine:
    """
    Paper trading engine that simulates order execution.
    Tracks virtual balances, positions, and performance metrics.
    """

    def __init__(
        self,
        initial_balances: Optional[Dict[str, Decimal]] = None,
        fee_config: Optional[ArbitrageConfig] = None,
        slippage_model: str = "orderbook",  # "orderbook", "fixed", "percentage"
        fixed_slippage_bps: Decimal = Decimal("5"),  # 5 basis points
    ):
        """
        Initialize the paper trading engine.

        Args:
            initial_balances: Initial asset balances (default: 10000 USDT)
            fee_config: Exchange fee configuration
            slippage_model: Slippage calculation model
            fixed_slippage_bps: Fixed slippage in basis points (for "fixed" model)
        """
        self.slippage_model = slippage_model
        self.fixed_slippage_bps = fixed_slippage_bps

        # Initialize fee config
        self.fee_config = fee_config or ArbitrageConfig()

        # Initialize balances
        self._balances: Dict[str, Balance] = {}
        initial = initial_balances or {"USDT": Decimal("10000")}
        for asset, amount in initial.items():
            self._balances[asset] = Balance(asset=asset, free=amount)

        # Track initial equity for performance metrics
        self._initial_equity = sum(b.total for b in self._balances.values())

        # Position and order tracking
        self._positions: Dict[str, Position] = {}  # key: symbol_exchange
        self._orders: Dict[str, PaperOrder] = {}  # key: order_id
        self._trades: List[PaperTrade] = []

        # Current orderbooks for realistic simulation
        self._orderbooks: Dict[str, OrderBook] = {}  # key: symbol_exchange

        # Performance metrics
        self._metrics = PerformanceMetrics(
            initial_equity=self._initial_equity,
            current_equity=self._initial_equity,
            peak_equity=self._initial_equity,
        )

        # Daily equity tracking for Sharpe calculation
        self._last_equity_date: Optional[datetime] = None
        self._last_equity: Decimal = self._initial_equity

        # Callbacks for trade events
        self._trade_callbacks: List[Callable[[PaperTrade], Any]] = []

        logger.info(
            "paper_trading_engine_initialized",
            initial_balances=initial,
            slippage_model=slippage_model,
        )

    def update_orderbook(self, orderbook: OrderBook) -> None:
        """
        Update the cached orderbook for a symbol/exchange.

        Args:
            orderbook: Current orderbook
        """
        key = f"{orderbook.symbol}_{orderbook.exchange}"
        self._orderbooks[key] = orderbook

        # Update position prices
        pos_key = f"{orderbook.symbol}_{orderbook.exchange}"
        if pos_key in self._positions:
            self._positions[pos_key].current_price = orderbook.mid_price or Decimal("0")

    def get_balance(self, asset: str) -> Balance:
        """
        Get balance for an asset.

        Args:
            asset: Asset symbol (e.g., "USDT", "BTC")

        Returns:
            Balance object
        """
        if asset not in self._balances:
            self._balances[asset] = Balance(asset=asset)
        return self._balances[asset]

    def get_all_balances(self) -> Dict[str, Balance]:
        """Get all asset balances."""
        return self._balances.copy()

    def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """
        Get position for a symbol/exchange.

        Args:
            symbol: Trading symbol
            exchange: Exchange name

        Returns:
            Position or None
        """
        key = f"{symbol}_{exchange}"
        return self._positions.get(key)

    def get_all_positions(self) -> List[Position]:
        """Get all open positions."""
        return list(self._positions.values())

    def calculate_slippage(
        self,
        symbol: str,
        exchange: str,
        side: OrderSide,
        quantity: Decimal,
        orderbook: Optional[OrderBook] = None,
    ) -> Decimal:
        """
        Calculate expected slippage for an order.

        Args:
            symbol: Trading symbol
            exchange: Exchange name
            side: Order side
            quantity: Order quantity
            orderbook: Optional orderbook (uses cached if not provided)

        Returns:
            Slippage as a percentage
        """
        if self.slippage_model == "fixed":
            return self.fixed_slippage_bps / Decimal("10000")

        if self.slippage_model == "percentage":
            # Simple percentage based on order size
            base_slippage = Decimal("0.0005")  # 0.05% base
            size_factor = min(quantity * Decimal("0.0001"), Decimal("0.005"))
            return base_slippage + size_factor

        # Orderbook-based slippage
        key = f"{symbol}_{exchange}"
        ob = orderbook or self._orderbooks.get(key)

        if not ob or not ob.bids or not ob.asks:
            # No orderbook data, use conservative estimate
            return Decimal("0.001")  # 0.1%

        # Simulate walking the orderbook
        remaining = quantity
        total_cost = Decimal("0")
        levels = ob.asks if side == OrderSide.BUY else ob.bids

        for level in levels:
            if remaining <= 0:
                break
            fill_qty = min(remaining, level.quantity)
            total_cost += fill_qty * level.price
            remaining -= fill_qty

        if remaining > 0:
            # Not enough liquidity
            logger.warning(
                "insufficient_liquidity",
                symbol=symbol,
                exchange=exchange,
                remaining=float(remaining),
            )
            # Add penalty for insufficient liquidity
            total_cost += remaining * (levels[-1].price if levels else Decimal("0")) * Decimal("1.01")

        # Calculate average fill price
        avg_price = total_cost / quantity
        mid_price = ob.mid_price or avg_price

        # Slippage is difference from mid price
        if side == OrderSide.BUY:
            slippage = (avg_price - mid_price) / mid_price
        else:
            slippage = (mid_price - avg_price) / mid_price

        return max(slippage, Decimal("0"))

    def calculate_fees(self, exchange: str, notional: Decimal, is_taker: bool = True) -> Decimal:
        """
        Calculate trading fees.

        Args:
            exchange: Exchange name
            notional: Notional value of the trade
            is_taker: Whether this is a taker order

        Returns:
            Fee amount
        """
        fees = self.fee_config.get_fees(exchange)
        fee_rate = fees.taker_fee if is_taker else fees.maker_fee
        return notional * fee_rate

    async def place_order(
        self,
        symbol: str,
        exchange: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Decimal] = None,
    ) -> PaperOrder:
        """
        Place a paper trading order.

        Args:
            symbol: Trading symbol
            exchange: Exchange name
            side: Order side (buy/sell)
            quantity: Order quantity
            order_type: Order type (market/limit)
            price: Limit price (required for limit orders)

        Returns:
            PaperOrder object
        """
        order_id = str(uuid.uuid4())[:8]

        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
        )

        self._orders[order_id] = order

        logger.info(
            "paper_order_placed",
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side.value,
            quantity=float(quantity),
            order_type=order_type.value,
        )

        # For market orders, execute immediately
        if order_type == OrderType.MARKET:
            await self._execute_market_order(order)

        return order

    async def _execute_market_order(self, order: PaperOrder) -> None:
        """
        Execute a market order with simulated fills.

        Args:
            order: The order to execute
        """
        key = f"{order.symbol}_{order.exchange}"
        orderbook = self._orderbooks.get(key)

        # Get execution price
        if orderbook:
            if order.side == OrderSide.BUY:
                base_price = orderbook.best_ask.price if orderbook.best_ask else Decimal("0")
            else:
                base_price = orderbook.best_bid.price if orderbook.best_bid else Decimal("0")
        else:
            # No orderbook data - reject order
            order.status = OrderStatus.REJECTED
            logger.warning("order_rejected_no_orderbook", order_id=order.order_id)
            return

        if base_price == 0:
            order.status = OrderStatus.REJECTED
            logger.warning("order_rejected_no_price", order_id=order.order_id)
            return

        # Calculate slippage
        slippage_pct = self.calculate_slippage(
            order.symbol, order.exchange, order.side, order.quantity, orderbook
        )

        # Apply slippage to price
        if order.side == OrderSide.BUY:
            fill_price = base_price * (1 + slippage_pct)
        else:
            fill_price = base_price * (1 - slippage_pct)

        # Calculate fees
        notional = fill_price * order.quantity
        fees = self.calculate_fees(order.exchange, notional, is_taker=True)

        # Check if we have sufficient balance
        base_asset, quote_asset = self._parse_symbol(order.symbol)

        if order.side == OrderSide.BUY:
            required = notional + fees
            available = self.get_balance(quote_asset).free
            if available < required:
                order.status = OrderStatus.REJECTED
                logger.warning(
                    "order_rejected_insufficient_balance",
                    order_id=order.order_id,
                    required=float(required),
                    available=float(available),
                )
                return
        else:
            available = self.get_balance(base_asset).free
            if available < order.quantity:
                order.status = OrderStatus.REJECTED
                logger.warning(
                    "order_rejected_insufficient_balance",
                    order_id=order.order_id,
                    required=float(order.quantity),
                    available=float(available),
                )
                return

        # Execute the trade
        await self._execute_fill(order, fill_price, order.quantity, fees, slippage_pct)

    async def _execute_fill(
        self,
        order: PaperOrder,
        fill_price: Decimal,
        fill_quantity: Decimal,
        fees: Decimal,
        slippage: Decimal,
    ) -> None:
        """
        Execute a fill and update balances/positions.

        Args:
            order: The order being filled
            fill_price: Execution price
            fill_quantity: Fill quantity
            fees: Trading fees
            slippage: Slippage percentage
        """
        base_asset, quote_asset = self._parse_symbol(order.symbol)

        # Update order
        order.filled_quantity = fill_quantity
        order.filled_price = fill_price
        order.slippage = slippage
        order.fees = fees
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()

        # Update balances
        notional = fill_price * fill_quantity

        if order.side == OrderSide.BUY:
            # Deduct quote currency + fees
            self._balances[quote_asset].free -= (notional + fees)
            # Add base currency
            if base_asset not in self._balances:
                self._balances[base_asset] = Balance(asset=base_asset)
            self._balances[base_asset].free += fill_quantity
        else:
            # Deduct base currency
            self._balances[base_asset].free -= fill_quantity
            # Add quote currency minus fees
            if quote_asset not in self._balances:
                self._balances[quote_asset] = Balance(asset=quote_asset)
            self._balances[quote_asset].free += (notional - fees)

        # Create trade record
        trade = PaperTrade(
            trade_id=str(uuid.uuid4())[:8],
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=fill_quantity,
            price=fill_price,
            fees=fees,
            slippage=slippage,
        )

        # Update position
        self._update_position(order, fill_price, fill_quantity, trade)

        self._trades.append(trade)

        # Update metrics
        self._update_metrics(trade)

        # Notify callbacks
        for callback in self._trade_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(trade)
                else:
                    callback(trade)
            except Exception as e:
                logger.error("trade_callback_error", error=str(e))

        logger.info(
            "paper_trade_executed",
            trade_id=trade.trade_id,
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side.value,
            quantity=float(fill_quantity),
            price=float(fill_price),
            fees=float(fees),
            slippage=float(slippage * 100),
        )

    def _update_position(
        self,
        order: PaperOrder,
        fill_price: Decimal,
        fill_quantity: Decimal,
        trade: PaperTrade,
    ) -> None:
        """
        Update position after a trade.

        Args:
            order: The filled order
            fill_price: Fill price
            fill_quantity: Fill quantity
            trade: Trade record
        """
        key = f"{order.symbol}_{order.exchange}"

        if key in self._positions:
            position = self._positions[key]

            if position.side == order.side:
                # Adding to position
                total_cost = position.entry_price * position.quantity + fill_price * fill_quantity
                total_qty = position.quantity + fill_quantity
                position.entry_price = total_cost / total_qty
                position.quantity = total_qty
            else:
                # Closing or reducing position
                close_qty = min(position.quantity, fill_quantity)
                remaining = fill_quantity - close_qty

                # Calculate PnL
                if position.side == OrderSide.BUY:
                    pnl = (fill_price - position.entry_price) * close_qty
                else:
                    pnl = (position.entry_price - fill_price) * close_qty

                pnl -= order.fees  # Subtract fees
                trade.pnl = pnl
                position.realized_pnl += pnl

                position.quantity -= close_qty

                if position.quantity <= 0:
                    del self._positions[key]
                    logger.info("position_closed", symbol=order.symbol, exchange=order.exchange)
                elif remaining > 0:
                    # Open new position in opposite direction
                    self._positions[key] = Position(
                        symbol=order.symbol,
                        exchange=order.exchange,
                        side=order.side,
                        entry_price=fill_price,
                        quantity=remaining,
                        current_price=fill_price,
                    )
        else:
            # New position
            self._positions[key] = Position(
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                entry_price=fill_price,
                quantity=fill_quantity,
                current_price=fill_price,
            )

    def _update_metrics(self, trade: PaperTrade) -> None:
        """
        Update performance metrics after a trade.

        Args:
            trade: The completed trade
        """
        self._metrics.total_trades += 1
        self._metrics.total_fees += trade.fees

        if trade.pnl > 0:
            self._metrics.winning_trades += 1
            if trade.pnl > self._metrics.largest_win:
                self._metrics.largest_win = trade.pnl
        elif trade.pnl < 0:
            self._metrics.losing_trades += 1
            if trade.pnl < self._metrics.largest_loss:
                self._metrics.largest_loss = trade.pnl

        self._metrics.total_pnl += trade.pnl

        # Update equity
        equity = self._calculate_equity()
        self._metrics.current_equity = equity

        # Update peak and drawdown
        if equity > self._metrics.peak_equity:
            self._metrics.peak_equity = equity
        else:
            drawdown = self._metrics.peak_equity - equity
            if drawdown > self._metrics.max_drawdown:
                self._metrics.max_drawdown = drawdown
                self._metrics.max_drawdown_percent = (
                    drawdown / self._metrics.peak_equity * 100
                    if self._metrics.peak_equity > 0
                    else Decimal("0")
                )

        # Track daily returns for Sharpe ratio
        now = datetime.now()
        if self._last_equity_date is None or now.date() > self._last_equity_date.date():
            if self._last_equity > 0:
                daily_return = (equity - self._last_equity) / self._last_equity
                self._metrics.daily_returns.append(daily_return)
            self._last_equity = equity
            self._last_equity_date = now

    def _calculate_equity(self) -> Decimal:
        """Calculate total equity including positions."""
        equity = Decimal("0")

        # Sum all balances (in USDT terms for simplicity)
        for asset, balance in self._balances.items():
            if asset == "USDT" or asset == "USD":
                equity += balance.total
            else:
                # Get current price from orderbooks
                for key, ob in self._orderbooks.items():
                    if key.startswith(f"{asset}/"):
                        if ob.mid_price:
                            equity += balance.total * ob.mid_price
                        break
                else:
                    # No price found, use last position price
                    for pos in self._positions.values():
                        if pos.symbol.startswith(f"{asset}/"):
                            equity += balance.total * pos.current_price
                            break

        return equity

    def _parse_symbol(self, symbol: str) -> tuple:
        """Parse symbol into base and quote assets."""
        if "/" in symbol:
            parts = symbol.split("/")
            return parts[0], parts[1]
        # Try common patterns
        for quote in ["USDT", "USD", "BUSD", "BTC", "ETH"]:
            if symbol.endswith(quote):
                return symbol[:-len(quote)], quote
        return symbol, "USDT"

    def get_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics."""
        # Update current equity
        self._metrics.current_equity = self._calculate_equity()
        return self._metrics

    def get_trades(self, limit: int = 100) -> List[PaperTrade]:
        """Get recent trades."""
        return self._trades[-limit:]

    def get_orders(self) -> Dict[str, PaperOrder]:
        """Get all orders."""
        return self._orders.copy()

    def subscribe_to_trades(self, callback: Callable[[PaperTrade], Any]) -> None:
        """
        Subscribe to trade notifications.

        Args:
            callback: Function to call when a trade is executed
        """
        self._trade_callbacks.append(callback)

    def reset(self, initial_balances: Optional[Dict[str, Decimal]] = None) -> None:
        """
        Reset the paper trading engine.

        Args:
            initial_balances: New initial balances (or use original)
        """
        initial = initial_balances or {"USDT": Decimal("10000")}

        self._balances.clear()
        for asset, amount in initial.items():
            self._balances[asset] = Balance(asset=asset, free=amount)

        self._initial_equity = sum(b.total for b in self._balances.values())
        self._positions.clear()
        self._orders.clear()
        self._trades.clear()

        self._metrics = PerformanceMetrics(
            initial_equity=self._initial_equity,
            current_equity=self._initial_equity,
            peak_equity=self._initial_equity,
        )

        self._last_equity_date = None
        self._last_equity = self._initial_equity

        logger.info("paper_trading_engine_reset", initial_balances=initial)

#!/usr/bin/env python3
"""
Paper Trading Dashboard - CLI interface for monitoring paper trading performance.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Optional
import signal
import argparse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.trading_bot.data import MultiExchangeManager
from src.trading_bot.paper_trading import (
    PaperTradingEngine,
    PaperTrade,
    OrderSide,
    OrderType,
)
from src.trading_bot.models import ArbitrageOpportunity
from src.trading_bot.core import get_logger

logger = get_logger(__name__)


class PaperTradingDashboard:
    """CLI dashboard for paper trading monitoring."""

    def __init__(
        self,
        initial_balance: Decimal = Decimal("10000"),
        auto_trade: bool = True,
        min_profit_threshold: Decimal = Decimal("0.2"),
    ):
        """
        Initialize the dashboard.

        Args:
            initial_balance: Initial USDT balance
            auto_trade: Automatically execute detected arbitrage opportunities
            min_profit_threshold: Minimum profit % to execute (for auto-trade)
        """
        self.initial_balance = initial_balance
        self.auto_trade = auto_trade
        self.min_profit_threshold = min_profit_threshold

        self.manager: Optional[MultiExchangeManager] = None
        self.engine: Optional[PaperTradingEngine] = None
        self.shutdown_event = asyncio.Event()

        # ANSI color codes
        self.GREEN = "\033[92m"
        self.YELLOW = "\033[93m"
        self.RED = "\033[91m"
        self.BLUE = "\033[94m"
        self.CYAN = "\033[96m"
        self.MAGENTA = "\033[95m"
        self.BOLD = "\033[1m"
        self.DIM = "\033[2m"
        self.RESET = "\033[0m"

    def clear_screen(self) -> None:
        """Clear terminal screen."""
        print("\033[2J\033[H", end="")

    def print_header(self) -> None:
        """Print dashboard header."""
        print("\n" + "=" * 100)
        print(f"{self.BOLD}{self.BLUE}Paper Trading Dashboard{self.RESET}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Initial Balance: ${float(self.initial_balance):,.2f} USDT")
        print(f"Auto-Trade: {'Enabled' if self.auto_trade else 'Disabled'}")
        if self.auto_trade:
            print(f"Min Profit Threshold: {float(self.min_profit_threshold):.2f}%")
        print("=" * 100)

    def print_balances(self) -> None:
        """Print current balances."""
        if not self.engine:
            return

        print(f"\n{self.BOLD}{self.CYAN}== BALANCES =={self.RESET}")
        print("-" * 50)
        print(f"{'Asset':<10} {'Free':<18} {'Locked':<18} {'Total':<18}")
        print("-" * 50)

        balances = self.engine.get_all_balances()
        for asset, balance in sorted(balances.items()):
            if balance.total > 0:
                print(
                    f"{asset:<10} "
                    f"{float(balance.free):>17,.6f} "
                    f"{float(balance.locked):>17,.6f} "
                    f"{float(balance.total):>17,.6f}"
                )

    def print_positions(self) -> None:
        """Print open positions."""
        if not self.engine:
            return

        positions = self.engine.get_all_positions()

        print(f"\n{self.BOLD}{self.CYAN}== OPEN POSITIONS =={self.RESET}")
        print("-" * 90)

        if not positions:
            print(f"{self.DIM}No open positions{self.RESET}")
            return

        print(f"{'Symbol':<12} {'Exchange':<12} {'Side':<6} {'Qty':<12} {'Entry':<12} {'Current':<12} {'PnL %':<10}")
        print("-" * 90)

        for pos in positions:
            pnl_color = self.GREEN if pos.unrealized_pnl >= 0 else self.RED
            print(
                f"{pos.symbol:<12} "
                f"{pos.exchange:<12} "
                f"{pos.side.value:<6} "
                f"{float(pos.quantity):>11,.6f} "
                f"${float(pos.entry_price):>10,.2f} "
                f"${float(pos.current_price):>10,.2f} "
                f"{pnl_color}{float(pos.unrealized_pnl_percent):>+9.2f}%{self.RESET}"
            )

    def print_recent_trades(self, limit: int = 10) -> None:
        """Print recent trades."""
        if not self.engine:
            return

        trades = self.engine.get_trades(limit)

        print(f"\n{self.BOLD}{self.CYAN}== RECENT TRADES =={self.RESET}")
        print("-" * 100)

        if not trades:
            print(f"{self.DIM}No trades executed yet{self.RESET}")
            return

        print(f"{'Time':<12} {'Symbol':<12} {'Exchange':<12} {'Side':<6} {'Qty':<10} {'Price':<12} {'Fees':<10} {'PnL':<12}")
        print("-" * 100)

        for trade in reversed(trades):
            time_str = trade.timestamp.strftime("%H:%M:%S")
            pnl_str = f"${float(trade.pnl):+,.2f}" if trade.pnl != 0 else "-"
            pnl_color = self.GREEN if trade.pnl > 0 else (self.RED if trade.pnl < 0 else self.RESET)

            print(
                f"{time_str:<12} "
                f"{trade.symbol:<12} "
                f"{trade.exchange:<12} "
                f"{trade.side.value:<6} "
                f"{float(trade.quantity):>9,.4f} "
                f"${float(trade.price):>10,.2f} "
                f"${float(trade.fees):>8,.4f} "
                f"{pnl_color}{pnl_str:<12}{self.RESET}"
            )

    def print_performance(self) -> None:
        """Print performance metrics."""
        if not self.engine:
            return

        metrics = self.engine.get_metrics()

        print(f"\n{self.BOLD}{self.CYAN}== PERFORMANCE METRICS =={self.RESET}")
        print("-" * 60)

        # Color code the return
        return_color = self.GREEN if metrics.return_percent >= 0 else self.RED

        print(f"{'Initial Equity:':<25} ${float(metrics.initial_equity):>15,.2f}")
        print(f"{'Current Equity:':<25} ${float(metrics.current_equity):>15,.2f}")
        print(f"{'Total Return:':<25} {return_color}{float(metrics.return_percent):>+14.2f}%{self.RESET}")
        print(f"{'Peak Equity:':<25} ${float(metrics.peak_equity):>15,.2f}")
        print(f"{'Max Drawdown:':<25} {self.RED}${float(metrics.max_drawdown):>15,.2f}{self.RESET}")
        print(f"{'Max Drawdown %:':<25} {self.RED}{float(metrics.max_drawdown_percent):>14.2f}%{self.RESET}")
        print("-" * 60)
        print(f"{'Total Trades:':<25} {metrics.total_trades:>15}")
        print(f"{'Winning Trades:':<25} {self.GREEN}{metrics.winning_trades:>15}{self.RESET}")
        print(f"{'Losing Trades:':<25} {self.RED}{metrics.losing_trades:>15}{self.RESET}")
        print(f"{'Win Rate:':<25} {float(metrics.win_rate):>14.1f}%")
        print(f"{'Total PnL:':<25} {return_color}${float(metrics.total_pnl):>+14,.2f}{self.RESET}")
        print(f"{'Total Fees:':<25} ${float(metrics.total_fees):>15,.2f}")
        print(f"{'Largest Win:':<25} {self.GREEN}${float(metrics.largest_win):>+14,.2f}{self.RESET}")
        print(f"{'Largest Loss:':<25} {self.RED}${float(metrics.largest_loss):>+14,.2f}{self.RESET}")

        # Sharpe ratio
        sharpe = metrics.calculate_sharpe_ratio()
        sharpe_color = self.GREEN if sharpe > 1 else (self.YELLOW if sharpe > 0 else self.RED)
        print(f"{'Sharpe Ratio (ann.):':<25} {sharpe_color}{float(sharpe):>15.2f}{self.RESET}")

    def print_dashboard(self) -> None:
        """Print the full dashboard."""
        self.clear_screen()
        self.print_header()
        self.print_balances()
        self.print_positions()
        self.print_recent_trades(limit=5)
        self.print_performance()
        print("\n" + "=" * 100)
        print(f"{self.DIM}Press Ctrl+C to exit | Dashboard refreshes every 10 seconds{self.RESET}")

    async def on_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """
        Handle detected arbitrage opportunity.

        Args:
            opportunity: Detected opportunity
        """
        if not self.auto_trade or not self.engine:
            return

        # Check if opportunity meets threshold
        if opportunity.profit_percent < self.min_profit_threshold:
            return

        # Check if we have sufficient balance
        base_asset, quote_asset = opportunity.symbol.split("/") if "/" in opportunity.symbol else (opportunity.symbol, "USDT")

        balance = self.engine.get_balance(quote_asset)
        order_size_quote = min(balance.free * Decimal("0.1"), Decimal("1000"))  # Use 10% of balance or $1000 max

        if order_size_quote < Decimal("50"):  # Minimum $50 order
            return

        # Calculate quantity
        quantity = order_size_quote / opportunity.buy_price

        logger.info(
            "auto_trading_opportunity",
            symbol=opportunity.symbol,
            buy_exchange=opportunity.buy_exchange,
            sell_exchange=opportunity.sell_exchange,
            profit_pct=float(opportunity.profit_percent),
            quantity=float(quantity),
        )

        # Execute buy on cheaper exchange
        await self.engine.place_order(
            symbol=opportunity.symbol,
            exchange=opportunity.buy_exchange,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
        )

        # Execute sell on more expensive exchange
        await self.engine.place_order(
            symbol=opportunity.symbol,
            exchange=opportunity.sell_exchange,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.MARKET,
        )

    async def on_trade(self, trade: PaperTrade) -> None:
        """
        Handle executed trade notification.

        Args:
            trade: Executed trade
        """
        pnl_str = f"${float(trade.pnl):+,.2f}" if trade.pnl != 0 else ""
        color = self.GREEN if trade.pnl > 0 else (self.RED if trade.pnl < 0 else self.YELLOW)

        print(
            f"\n{color}{self.BOLD}[TRADE]{self.RESET} "
            f"{trade.side.value.upper()} {float(trade.quantity):.4f} {trade.symbol} "
            f"@ ${float(trade.price):,.2f} on {trade.exchange} "
            f"(fees: ${float(trade.fees):.4f}, slip: {float(trade.slippage * 100):.3f}%) "
            f"{pnl_str}"
        )

    async def run(self) -> None:
        """Run the paper trading dashboard."""
        self.print_header()

        try:
            # Initialize paper trading engine
            self.engine = PaperTradingEngine(
                initial_balances={"USDT": self.initial_balance},
                slippage_model="orderbook",
            )

            # Subscribe to trade notifications
            self.engine.subscribe_to_trades(self.on_trade)

            # Initialize multi-exchange manager with mock exchange for testing
            self.manager = MultiExchangeManager(
                enable_arbitrage=True,
                enable_mock_exchange=True,
            )

            await self.manager.start()

            # Connect orderbook updates to paper trading engine
            def orderbook_callback(ob):
                self.engine.update_orderbook(ob)

            # The manager already subscribes to orderbooks, but we need to feed them to the engine
            # This is done via the arbitrage detector callbacks

            # Subscribe to arbitrage opportunities for auto-trading
            if self.auto_trade:
                self.manager.subscribe_to_opportunities(self.on_opportunity)

            logger.info(
                "paper_trading_dashboard_started",
                auto_trade=self.auto_trade,
                initial_balance=float(self.initial_balance),
            )

            # Refresh dashboard periodically
            async def refresh_dashboard():
                while not self.shutdown_event.is_set():
                    await asyncio.sleep(10)
                    if not self.shutdown_event.is_set():
                        self.print_dashboard()

            refresh_task = asyncio.create_task(refresh_dashboard())

            # Wait for shutdown
            await self.shutdown_event.wait()

            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            logger.error("dashboard_error", error=str(e), exc_info=True)
            print(f"\n{self.RED}Error: {str(e)}{self.RESET}")
        finally:
            if self.manager:
                await self.manager.stop()

            # Print final performance
            print("\n")
            self.print_performance()

    def handle_shutdown(self, signum: int) -> None:
        """Handle shutdown signal."""
        print(f"\n{self.YELLOW}Shutting down...{self.RESET}")
        self.shutdown_event.set()


async def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(description="Paper Trading Dashboard")
    parser.add_argument(
        "--balance",
        type=float,
        default=10000,
        help="Initial USDT balance (default: 10000)",
    )
    parser.add_argument(
        "--no-auto-trade",
        action="store_true",
        help="Disable automatic trading of arbitrage opportunities",
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=0.2,
        help="Minimum profit %% for auto-trade (default: 0.2)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Run for specified duration in seconds",
    )

    args = parser.parse_args()

    dashboard = PaperTradingDashboard(
        initial_balance=Decimal(str(args.balance)),
        auto_trade=not args.no_auto_trade,
        min_profit_threshold=Decimal(str(args.min_profit)),
    )

    # Set up signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: dashboard.handle_shutdown(s))

    # Run dashboard
    if args.duration:
        try:
            await asyncio.wait_for(dashboard.run(), timeout=args.duration)
        except asyncio.TimeoutError:
            print(f"\n{dashboard.YELLOW}Duration limit reached{dashboard.RESET}")
            dashboard.handle_shutdown(0)
    else:
        await dashboard.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        logger.error("main_error", error=str(e), exc_info=True)
        sys.exit(1)

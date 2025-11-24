#!/usr/bin/env python3
"""
Real-time arbitrage opportunity monitor.
Displays detected opportunities in a formatted table.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import signal

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.trading_bot.data import MultiExchangeManager
from src.trading_bot.models import ArbitrageOpportunity
from src.trading_bot.core import get_logger

logger = get_logger(__name__)


class ArbitrageMonitor:
    """Real-time arbitrage opportunity monitor with CLI display."""

    def __init__(self, enable_mock: bool = True):
        """
        Initialize the monitor.

        Args:
            enable_mock: Enable mock exchange for testing
        """
        self.manager: Optional[MultiExchangeManager] = None
        self.enable_mock = enable_mock
        self.opportunity_count = 0
        self.shutdown_event = asyncio.Event()

        # ANSI color codes for terminal output
        self.GREEN = "\033[92m"
        self.YELLOW = "\033[93m"
        self.RED = "\033[91m"
        self.BLUE = "\033[94m"
        self.BOLD = "\033[1m"
        self.RESET = "\033[0m"

    def print_header(self) -> None:
        """Print monitor header."""
        print("\n" + "=" * 100)
        print(f"{self.BOLD}{self.BLUE}Crypto Arbitrage Monitor{self.RESET}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 100)
        print(
            f"\n{self.BOLD}{'Time':<12} {'Symbol':<10} {'Buy':<15} {'Sell':<15} "
            f"{'Buy Price':<12} {'Sell Price':<12} {'Profit %':<10} {'Qty':<8}{self.RESET}"
        )
        print("-" * 100)

    async def on_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """
        Handle detected arbitrage opportunity.

        Args:
            opportunity: Detected arbitrage opportunity
        """
        self.opportunity_count += 1

        # Determine color based on profit level
        if opportunity.profit_percent > 0.5:
            color = self.GREEN
        elif opportunity.profit_percent > 0.3:
            color = self.YELLOW
        else:
            color = self.RESET

        # Format timestamp
        timestamp = datetime.fromtimestamp(opportunity.timestamp / 1000).strftime(
            "%H:%M:%S"
        )

        # Print opportunity
        print(
            f"{color}{timestamp:<12} {opportunity.symbol:<10} "
            f"{opportunity.buy_exchange:<15} {opportunity.sell_exchange:<15} "
            f"${float(opportunity.buy_price):<11.2f} ${float(opportunity.sell_price):<11.2f} "
            f"{float(opportunity.profit_percent):>8.3f}% {float(opportunity.buy_quantity):<7.4f}{self.RESET}"
        )

        # Log to file
        logger.info(
            "arbitrage_opportunity",
            count=self.opportunity_count,
            symbol=opportunity.symbol,
            buy_exchange=opportunity.buy_exchange,
            sell_exchange=opportunity.sell_exchange,
            buy_price=float(opportunity.buy_price),
            sell_price=float(opportunity.sell_price),
            profit_pct=float(opportunity.profit_percent),
            quantity=float(opportunity.buy_quantity),
        )

    def print_statistics(self) -> None:
        """Print statistics summary."""
        if not self.manager or not self.manager.arbitrage_detector:
            return

        stats = self.manager.get_statistics()

        print("\n" + "=" * 100)
        print(f"{self.BOLD}{self.BLUE}Statistics Summary{self.RESET}")
        print("-" * 100)
        print(f"Total Opportunities Detected: {stats['total_detected']}")
        print(f"Profitable Opportunities: {stats['total_profitable']}")
        print(f"Success Rate: {stats['success_rate_pct']:.2f}%")
        print(f"Average Profit: {stats['avg_profit_pct']:.3f}%")

        if stats.get("best_opportunity"):
            best = stats["best_opportunity"]
            print(
                f"\n{self.GREEN}Best Opportunity:{self.RESET} "
                f"{best['symbol']} - {best['profit_pct']:.3f}% "
                f"({best['buy_exchange']} -> {best['sell_exchange']})"
            )

        if stats.get("opportunities_by_pair"):
            print(f"\n{self.BOLD}Opportunities by Pair:{self.RESET}")
            for pair, count in sorted(
                stats["opportunities_by_pair"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]:
                print(f"  {pair}: {count}")

        print("=" * 100)

    def print_top_opportunities(self) -> None:
        """Print top opportunities by profitability."""
        if not self.manager:
            return

        opportunities = self.manager.get_ranked_opportunities(limit=5)

        if opportunities:
            print(f"\n{self.BOLD}{self.BLUE}Top 5 Opportunities:{self.RESET}")
            print("-" * 100)
            for i, opp in enumerate(opportunities, 1):
                print(
                    f"{i}. {opp.symbol} - {float(opp.profit_percent):.3f}% "
                    f"({opp.buy_exchange} -> {opp.sell_exchange}) "
                    f"[${float(opp.buy_price):.2f} -> ${float(opp.sell_price):.2f}]"
                )

    async def run(self) -> None:
        """Run the arbitrage monitor."""
        self.print_header()

        try:
            # Initialize multi-exchange manager
            self.manager = MultiExchangeManager(
                enable_arbitrage=True,
                enable_mock_exchange=self.enable_mock,
            )

            await self.manager.start()

            # Subscribe to opportunities
            self.manager.subscribe_to_opportunities(self.on_opportunity)

            logger.info("arbitrage_monitor_started", enable_mock=self.enable_mock)

            # Print status every 30 seconds
            async def print_periodic_status():
                while not self.shutdown_event.is_set():
                    await asyncio.sleep(30)
                    if not self.shutdown_event.is_set():
                        self.print_statistics()
                        self.print_top_opportunities()

            status_task = asyncio.create_task(print_periodic_status())

            # Wait for shutdown
            await self.shutdown_event.wait()

            # Cancel status task
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            logger.error("monitor_error", error=str(e), exc_info=True)
            print(f"\n{self.RED}Error: {str(e)}{self.RESET}")
        finally:
            if self.manager:
                await self.manager.stop()

            # Print final statistics
            print("\n")
            self.print_statistics()
            self.print_top_opportunities()

    def handle_shutdown(self, signum: int) -> None:
        """
        Handle shutdown signal.

        Args:
            signum: Signal number
        """
        print(f"\n{self.YELLOW}Shutting down...{self.RESET}")
        self.shutdown_event.set()


async def main() -> None:
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Monitor arbitrage opportunities")
    parser.add_argument(
        "--no-mock",
        action="store_true",
        help="Disable mock exchange (only use Binance testnet)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Run for specified duration in seconds (default: run until interrupted)",
    )

    args = parser.parse_args()

    monitor = ArbitrageMonitor(enable_mock=not args.no_mock)

    # Set up signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: monitor.handle_shutdown(s))

    # Run monitor
    if args.duration:
        # Run for specified duration
        try:
            await asyncio.wait_for(monitor.run(), timeout=args.duration)
        except asyncio.TimeoutError:
            print(f"\n{monitor.YELLOW}Duration limit reached{monitor.RESET}")
            monitor.handle_shutdown(0)
    else:
        # Run until interrupted
        await monitor.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        logger.error("main_error", error=str(e), exc_info=True)
        sys.exit(1)

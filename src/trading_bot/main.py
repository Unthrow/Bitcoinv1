"""
Main entry point for the trading bot.
"""

import asyncio
import signal
from typing import Optional

from .core.config import config
from .core.logging_config import get_logger
from .data.data_manager import DataManager

logger = get_logger(__name__)


class TradingBot:
    """Main trading bot application."""

    def __init__(self) -> None:
        """Initialize the trading bot."""
        self.data_manager: Optional[DataManager] = None
        self._shutdown_event = asyncio.Event()

        logger.info(
            "trading_bot_initialized",
            environment=config.environment,
            symbols=config.trading.default_symbols,
        )

    async def start(self) -> None:
        """Start the trading bot."""
        logger.info("starting_trading_bot")

        try:
            # Initialize and start DataManager
            self.data_manager = DataManager()
            await self.data_manager.start()

            logger.info("trading_bot_started", status="running")

            # Wait for shutdown signal
            await self._shutdown_event.wait()

        except Exception as e:
            logger.error("trading_bot_error", error=str(e), exc_info=True)
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the trading bot."""
        logger.info("stopping_trading_bot")

        if self.data_manager:
            await self.data_manager.stop()

        logger.info("trading_bot_stopped")

    def handle_shutdown(self, signum: int) -> None:
        """
        Handle shutdown signals.

        Args:
            signum: Signal number
        """
        logger.info("shutdown_signal_received", signal=signum)
        self._shutdown_event.set()


async def main() -> None:
    """Main async function."""
    bot = TradingBot()

    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: bot.handle_shutdown(s))

    # Start the bot
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())

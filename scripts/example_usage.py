#!/usr/bin/env python3
"""
Example usage of the trading bot's DataManager.
This script demonstrates how to stream and access market data.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.trading_bot.data import DataManager
from src.trading_bot.models import OrderBook
from src.trading_bot.core import get_logger

logger = get_logger(__name__)


async def on_orderbook_update(orderbook: OrderBook) -> None:
    """
    Callback for order book updates.

    Args:
        orderbook: Updated order book
    """
    if orderbook.best_bid and orderbook.best_ask:
        logger.info(
            "orderbook_update",
            symbol=orderbook.symbol,
            best_bid=float(orderbook.best_bid.price),
            best_ask=float(orderbook.best_ask.price),
            spread=float(orderbook.spread) if orderbook.spread else None,
            mid_price=float(orderbook.mid_price) if orderbook.mid_price else None,
        )


async def main() -> None:
    """Main function demonstrating DataManager usage."""
    logger.info("starting_example")

    async with DataManager() as data_manager:
        logger.info("data_manager_started")

        # Subscribe to order book updates for specific symbols
        data_manager.subscribe("orderbook:BTCUSDT", on_orderbook_update)
        data_manager.subscribe("orderbook:ETHUSDT", on_orderbook_update)

        # Let it run for 30 seconds to collect data
        logger.info("collecting_data", duration_seconds=30)
        await asyncio.sleep(30)

        # Get latest order books
        for symbol in ["BTCUSDT", "ETHUSDT", "BNBUSDT"]:
            orderbook = await data_manager.get_orderbook(symbol)
            if orderbook and orderbook.best_bid and orderbook.best_ask:
                logger.info(
                    "current_orderbook",
                    symbol=symbol,
                    best_bid=float(orderbook.best_bid.price),
                    best_ask=float(orderbook.best_ask.price),
                    spread_bps=float(orderbook.spread / orderbook.mid_price * 10000)
                    if orderbook.spread and orderbook.mid_price
                    else None,
                )

        logger.info("example_completed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("interrupted_by_user")
    except Exception as e:
        logger.error("example_failed", error=str(e), exc_info=True)
        sys.exit(1)

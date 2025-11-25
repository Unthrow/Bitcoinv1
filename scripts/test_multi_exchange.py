#!/usr/bin/env python3
"""
Test script for multi-exchange orderbook fetching.
Tests BTC/USDT (or equivalent) across Binance, Coinbase, and Kraken.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.trading_bot.data.binance_client import BinanceClient
from src.trading_bot.exchanges.coinbase_client import CoinbaseClient
from src.trading_bot.exchanges.kraken_client import KrakenClient
from src.trading_bot.utils.symbol_mapping import SymbolMapper
from src.trading_bot.core import get_logger

logger = get_logger(__name__)

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header():
    """Print test header."""
    print("\n" + "=" * 90)
    print(f"{BOLD}{BLUE}Multi-Exchange Orderbook Test{RESET}")
    print(f"Testing BTC/USDT across Binance, Coinbase, and Kraken")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)


def print_orderbook(exchange: str, symbol: str, orderbook: Any):
    """Print orderbook data in a formatted way."""
    print(f"\n{BOLD}{CYAN}--- {exchange.upper()} ---{RESET}")
    print(f"Symbol: {symbol}")
    print(f"Timestamp: {datetime.fromtimestamp(orderbook.timestamp / 1000).strftime('%H:%M:%S.%f')[:-3]}")

    if orderbook.best_bid and orderbook.best_ask:
        print(f"{GREEN}Best Bid: ${float(orderbook.best_bid.price):,.2f} (qty: {float(orderbook.best_bid.quantity):.6f}){RESET}")
        print(f"{RED}Best Ask: ${float(orderbook.best_ask.price):,.2f} (qty: {float(orderbook.best_ask.quantity):.6f}){RESET}")
        print(f"Spread: ${float(orderbook.spread):,.2f} ({float(orderbook.spread / orderbook.mid_price * 100):.4f}%)")
        print(f"Mid Price: ${float(orderbook.mid_price):,.2f}")
    else:
        print(f"{RED}No orderbook data available{RESET}")

    # Show top 3 bids and asks
    print(f"\n{BOLD}Top 3 Bids:{RESET}")
    for i, bid in enumerate(orderbook.bids[:3]):
        print(f"  {i+1}. ${float(bid.price):,.2f} x {float(bid.quantity):.6f}")

    print(f"\n{BOLD}Top 3 Asks:{RESET}")
    for i, ask in enumerate(orderbook.asks[:3]):
        print(f"  {i+1}. ${float(ask.price):,.2f} x {float(ask.quantity):.6f}")


def print_comparison(orderbooks: Dict[str, Any]):
    """Print price comparison across exchanges."""
    print("\n" + "=" * 90)
    print(f"{BOLD}{BLUE}Price Comparison Across Exchanges{RESET}")
    print("-" * 90)

    prices = {}
    for exchange, ob in orderbooks.items():
        if ob and ob.best_bid and ob.best_ask:
            prices[exchange] = {
                "bid": float(ob.best_bid.price),
                "ask": float(ob.best_ask.price),
                "mid": float(ob.mid_price),
            }

    if not prices:
        print(f"{RED}No price data available for comparison{RESET}")
        return

    # Print price table
    print(f"\n{'Exchange':<15} {'Best Bid':<15} {'Best Ask':<15} {'Mid Price':<15} {'Spread %':<10}")
    print("-" * 70)

    for exchange, p in sorted(prices.items()):
        spread_pct = (p["ask"] - p["bid"]) / p["mid"] * 100
        print(f"{exchange:<15} ${p['bid']:<14,.2f} ${p['ask']:<14,.2f} ${p['mid']:<14,.2f} {spread_pct:<9.4f}%")

    # Calculate arbitrage opportunities
    print(f"\n{BOLD}{YELLOW}Potential Arbitrage Opportunities:{RESET}")
    print("-" * 70)

    exchanges = list(prices.keys())
    opportunities_found = False

    for i, buy_exchange in enumerate(exchanges):
        for sell_exchange in exchanges[i+1:]:
            buy_price = prices[buy_exchange]["ask"]  # We buy at ask
            sell_price = prices[sell_exchange]["bid"]  # We sell at bid

            # Check both directions
            for buy_ex, sell_ex, buy_p, sell_p in [
                (buy_exchange, sell_exchange, buy_price, prices[sell_exchange]["bid"]),
                (sell_exchange, buy_exchange, prices[sell_exchange]["ask"], prices[buy_exchange]["bid"]),
            ]:
                if sell_p > buy_p:
                    gross_profit_pct = (sell_p - buy_p) / buy_p * 100
                    # Rough estimate: ~0.2% total fees for round trip
                    net_profit_pct = gross_profit_pct - 0.2

                    color = GREEN if net_profit_pct > 0 else YELLOW
                    opportunities_found = True
                    print(
                        f"{color}Buy on {buy_ex} @ ${buy_p:,.2f}, "
                        f"Sell on {sell_ex} @ ${sell_p:,.2f} -> "
                        f"Gross: {gross_profit_pct:.4f}%, "
                        f"Net (est): {net_profit_pct:.4f}%{RESET}"
                    )

    if not opportunities_found:
        print(f"  No arbitrage opportunities detected (prices are too close)")

    print("=" * 90)


async def test_exchange(client: Any, symbol: str, exchange_name: str) -> Any:
    """
    Test fetching orderbook from a single exchange.

    Args:
        client: Exchange client
        symbol: Trading symbol
        exchange_name: Name of the exchange

    Returns:
        OrderBook or None if failed
    """
    try:
        print(f"\n{CYAN}Fetching orderbook from {exchange_name}...{RESET}")
        orderbook = await client.get_orderbook(symbol, limit=10)
        print(f"{GREEN}Successfully fetched {exchange_name} orderbook{RESET}")
        return orderbook
    except Exception as e:
        print(f"{RED}Failed to fetch {exchange_name} orderbook: {str(e)}{RESET}")
        logger.error(f"exchange_test_failed", exchange=exchange_name, error=str(e), exc_info=True)
        return None


async def main():
    """Main test function."""
    print_header()

    # Test symbol
    test_symbol = "BTC/USDT"
    print(f"\n{BOLD}Test Symbol: {test_symbol}{RESET}")
    print(f"\nExchange symbol mappings:")
    mappings = SymbolMapper.get_equivalent_pairs(test_symbol)
    for exchange, symbol in mappings.items():
        if exchange != "mock_exchange":
            print(f"  - {exchange}: {symbol}")

    # Initialize clients
    print(f"\n{BOLD}Initializing exchange clients...{RESET}")

    binance_client = BinanceClient()
    coinbase_client = CoinbaseClient(use_sandbox=False)
    kraken_client = KrakenClient()

    orderbooks: Dict[str, Any] = {}

    try:
        # Fetch orderbooks from all exchanges concurrently
        print(f"\n{BOLD}Fetching orderbooks...{RESET}")

        results = await asyncio.gather(
            test_exchange(binance_client, test_symbol, "binance"),
            test_exchange(coinbase_client, test_symbol, "coinbase"),
            test_exchange(kraken_client, test_symbol, "kraken"),
            return_exceptions=True,
        )

        exchange_names = ["binance", "coinbase", "kraken"]
        for name, result in zip(exchange_names, results):
            if isinstance(result, Exception):
                print(f"{RED}Error from {name}: {str(result)}{RESET}")
                orderbooks[name] = None
            else:
                orderbooks[name] = result

        # Print individual orderbooks
        for exchange, ob in orderbooks.items():
            if ob:
                print_orderbook(exchange, test_symbol, ob)

        # Print comparison
        print_comparison(orderbooks)

        # Summary
        successful = sum(1 for ob in orderbooks.values() if ob is not None)
        print(f"\n{BOLD}Summary:{RESET}")
        print(f"Successfully fetched orderbooks from {successful}/{len(orderbooks)} exchanges")

        if successful == len(orderbooks):
            print(f"{GREEN}All exchanges operational!{RESET}")
        elif successful > 0:
            print(f"{YELLOW}Some exchanges failed - check logs for details{RESET}")
        else:
            print(f"{RED}All exchanges failed - check network/API access{RESET}")

    finally:
        # Cleanup
        print(f"\n{CYAN}Closing connections...{RESET}")
        await binance_client.close()
        await coinbase_client.close()
        await kraken_client.close()
        print(f"{GREEN}Done!{RESET}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted.")
    except Exception as e:
        print(f"\n{RED}Test failed: {str(e)}{RESET}")
        logger.error("test_failed", error=str(e), exc_info=True)
        sys.exit(1)

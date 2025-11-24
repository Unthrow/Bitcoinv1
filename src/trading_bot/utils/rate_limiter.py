"""
Rate limiter for API requests.
Implements token bucket algorithm for exchange API rate limiting.
"""

import asyncio
import time
from typing import Dict, Optional
from dataclasses import dataclass

from ..core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_second: float
    burst_size: int = 10


class RateLimiter:
    """
    Token bucket rate limiter for API requests.
    Ensures we don't exceed exchange API rate limits.
    """

    def __init__(self, config: RateLimitConfig):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration
        """
        self.requests_per_second = config.requests_per_second
        self.burst_size = config.burst_size

        # Token bucket
        self.tokens = float(self.burst_size)
        self.last_update = time.time()

        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(
            "rate_limiter_initialized",
            requests_per_second=self.requests_per_second,
            burst_size=self.burst_size,
        )

    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens for making requests.
        Blocks if insufficient tokens are available.

        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        async with self._lock:
            while True:
                # Refill tokens based on time elapsed
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + elapsed * self.requests_per_second,
                )
                self.last_update = now

                # Check if we have enough tokens
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Wait until we have enough tokens
                wait_time = (tokens - self.tokens) / self.requests_per_second
                await asyncio.sleep(wait_time)


class ExchangeRateLimiters:
    """
    Manages rate limiters for different exchanges.
    """

    # Rate limits for different exchanges (requests per second)
    EXCHANGE_LIMITS: Dict[str, RateLimitConfig] = {
        "binance": RateLimitConfig(requests_per_second=10.0, burst_size=20),
        "binance_testnet": RateLimitConfig(requests_per_second=10.0, burst_size=20),
        "coinbase": RateLimitConfig(requests_per_second=3.0, burst_size=10),
        "kraken": RateLimitConfig(requests_per_second=1.0, burst_size=5),
        "mock_exchange": RateLimitConfig(requests_per_second=100.0, burst_size=100),
    }

    def __init__(self):
        """Initialize exchange rate limiters."""
        self._limiters: Dict[str, RateLimiter] = {}

    def get_limiter(self, exchange: str) -> RateLimiter:
        """
        Get rate limiter for an exchange.

        Args:
            exchange: Exchange name

        Returns:
            RateLimiter instance
        """
        if exchange not in self._limiters:
            config = self.EXCHANGE_LIMITS.get(
                exchange,
                RateLimitConfig(requests_per_second=1.0, burst_size=5),  # Conservative default
            )
            self._limiters[exchange] = RateLimiter(config)
            logger.info("rate_limiter_created", exchange=exchange)

        return self._limiters[exchange]

    async def acquire(self, exchange: str, tokens: int = 1) -> None:
        """
        Acquire tokens for an exchange.

        Args:
            exchange: Exchange name
            tokens: Number of tokens to acquire
        """
        limiter = self.get_limiter(exchange)
        await limiter.acquire(tokens)


# Global rate limiter instance
rate_limiters = ExchangeRateLimiters()

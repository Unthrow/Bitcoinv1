"""
Exchange fee configurations and trading parameters.
"""

from decimal import Decimal
from typing import Dict
from pydantic import BaseModel, Field


class ExchangeFees(BaseModel):
    """Fee structure for an exchange."""

    maker_fee: Decimal = Field(default=Decimal("0.001"), description="Maker fee (0.1%)")
    taker_fee: Decimal = Field(default=Decimal("0.001"), description="Taker fee (0.1%)")
    withdrawal_fee: Decimal = Field(
        default=Decimal("0.0005"), description="Withdrawal fee (0.05%)"
    )

    @property
    def total_roundtrip_fee(self) -> Decimal:
        """Calculate total fee for a complete arbitrage roundtrip (buy + sell)."""
        return self.taker_fee * 2 + self.withdrawal_fee


class ArbitrageConfig(BaseModel):
    """Configuration for arbitrage detection."""

    min_profit_percent: Decimal = Field(
        default=Decimal("0.15"), description="Minimum profit % after fees"
    )
    safety_margin: Decimal = Field(
        default=Decimal("0.05"), description="Additional safety margin %"
    )
    max_slippage_percent: Decimal = Field(
        default=Decimal("0.1"), description="Maximum acceptable slippage %"
    )
    min_order_size_usd: Decimal = Field(
        default=Decimal("100"), description="Minimum order size in USD"
    )
    max_order_size_usd: Decimal = Field(
        default=Decimal("10000"), description="Maximum order size in USD"
    )

    # Exchange-specific fees
    exchange_fees: Dict[str, ExchangeFees] = Field(default_factory=dict)

    def __init__(self, **kwargs):  # type: ignore
        super().__init__(**kwargs)
        # Default fees for common exchanges
        if not self.exchange_fees:
            self.exchange_fees = {
                "binance": ExchangeFees(
                    maker_fee=Decimal("0.001"),
                    taker_fee=Decimal("0.001"),
                    withdrawal_fee=Decimal("0.0005"),
                ),
                "binance_testnet": ExchangeFees(
                    maker_fee=Decimal("0.001"),
                    taker_fee=Decimal("0.001"),
                    withdrawal_fee=Decimal("0.0005"),
                ),
                "coinbase": ExchangeFees(
                    maker_fee=Decimal("0.004"),  # 0.4% maker
                    taker_fee=Decimal("0.006"),  # 0.6% taker
                    withdrawal_fee=Decimal("0.0010"),  # 0.1% withdrawal
                ),
                "kraken": ExchangeFees(
                    maker_fee=Decimal("0.0016"),  # 0.16% maker
                    taker_fee=Decimal("0.0026"),  # 0.26% taker
                    withdrawal_fee=Decimal("0.0009"),  # 0.09% withdrawal
                ),
                "mock_exchange": ExchangeFees(
                    maker_fee=Decimal("0.0015"),
                    taker_fee=Decimal("0.0015"),
                    withdrawal_fee=Decimal("0.0008"),
                ),
            }

    def get_fees(self, exchange: str) -> ExchangeFees:
        """
        Get fee structure for an exchange.

        Args:
            exchange: Exchange name

        Returns:
            ExchangeFees instance
        """
        return self.exchange_fees.get(
            exchange, ExchangeFees()  # Default fees if not configured
        )

    @property
    def effective_min_profit(self) -> Decimal:
        """Get effective minimum profit including safety margin."""
        return self.min_profit_percent + self.safety_margin

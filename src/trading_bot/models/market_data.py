"""
Data models for market data structures.
All models use Pydantic for validation and serialization.
"""

from typing import List, Tuple
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


class PriceLevel(BaseModel):
    """Represents a single price level in the order book."""

    price: Decimal
    quantity: Decimal

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def convert_to_decimal(cls, v: str | float | Decimal) -> Decimal:
        """Convert price/quantity to Decimal for precision."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class OrderBook(BaseModel):
    """Order book snapshot with bids and asks."""

    exchange: str
    symbol: str
    timestamp: int  # Unix timestamp in milliseconds
    bids: List[PriceLevel] = Field(default_factory=list)
    asks: List[PriceLevel] = Field(default_factory=list)
    last_update_id: int = 0

    @field_validator("bids", "asks", mode="before")
    @classmethod
    def parse_price_levels(
        cls, v: List[Tuple[str | float, str | float]] | List[PriceLevel]
    ) -> List[PriceLevel]:
        """Parse price levels from various formats."""
        if not v:
            return []

        if isinstance(v[0], PriceLevel):
            return v

        return [PriceLevel(price=price, quantity=qty) for price, qty in v]

    @property
    def best_bid(self) -> PriceLevel | None:
        """Get the best bid (highest buy price)."""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> PriceLevel | None:
        """Get the best ask (lowest sell price)."""
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> Decimal | None:
        """Calculate the bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return None

    @property
    def mid_price(self) -> Decimal | None:
        """Calculate the mid-market price."""
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / Decimal("2")
        return None


class Trade(BaseModel):
    """Represents a single trade."""

    exchange: str
    symbol: str
    trade_id: str
    price: Decimal
    quantity: Decimal
    side: str  # "buy" or "sell"
    timestamp: int  # Unix timestamp in milliseconds
    is_buyer_maker: bool = False

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def convert_to_decimal(cls, v: str | float | Decimal) -> Decimal:
        """Convert price/quantity to Decimal for precision."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        """Validate trade side."""
        side = v.lower()
        if side not in ["buy", "sell"]:
            raise ValueError(f"Invalid side: {v}. Must be 'buy' or 'sell'")
        return side


class Ticker(BaseModel):
    """24-hour ticker statistics."""

    exchange: str
    symbol: str
    timestamp: int
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    quote_volume: Decimal
    price_change: Decimal
    price_change_percent: Decimal

    @field_validator(
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "quote_volume",
        "price_change",
        "price_change_percent",
        mode="before",
    )
    @classmethod
    def convert_to_decimal(cls, v: str | float | Decimal) -> Decimal:
        """Convert numeric fields to Decimal for precision."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class ArbitrageOpportunity(BaseModel):
    """Represents a detected arbitrage opportunity."""

    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: Decimal
    sell_price: Decimal
    profit_percent: Decimal
    timestamp: int
    buy_quantity: Decimal = Decimal("0")
    sell_quantity: Decimal = Decimal("0")

    @field_validator("buy_price", "sell_price", "profit_percent", "buy_quantity", "sell_quantity", mode="before")
    @classmethod
    def convert_to_decimal(cls, v: str | float | Decimal) -> Decimal:
        """Convert numeric fields to Decimal for precision."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @property
    def is_profitable(self) -> bool:
        """Check if the opportunity is profitable after fees."""
        # Simple check - should be enhanced with actual fee calculation
        return self.profit_percent > Decimal("0.3")  # 0.3% minimum profit

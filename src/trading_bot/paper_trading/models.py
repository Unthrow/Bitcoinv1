"""
Data models for paper trading system.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator


class OrderSide(str, Enum):
    """Order side enum."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enum."""
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Order status enum."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Balance(BaseModel):
    """Represents the balance of a single asset."""

    asset: str
    free: Decimal = Decimal("0")
    locked: Decimal = Decimal("0")

    @field_validator("free", "locked", mode="before")
    @classmethod
    def convert_to_decimal(cls, v) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @property
    def total(self) -> Decimal:
        """Total balance (free + locked)."""
        return self.free + self.locked


class Position(BaseModel):
    """Represents a trading position."""

    symbol: str
    exchange: str
    side: OrderSide
    entry_price: Decimal
    quantity: Decimal
    current_price: Decimal = Decimal("0")
    opened_at: datetime = Field(default_factory=datetime.now)
    realized_pnl: Decimal = Decimal("0")

    @field_validator("entry_price", "quantity", "current_price", "realized_pnl", mode="before")
    @classmethod
    def convert_to_decimal(cls, v) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @property
    def unrealized_pnl(self) -> Decimal:
        """Calculate unrealized profit/loss."""
        if self.side == OrderSide.BUY:
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity

    @property
    def unrealized_pnl_percent(self) -> Decimal:
        """Calculate unrealized PnL as percentage."""
        if self.entry_price == 0:
            return Decimal("0")
        return (self.unrealized_pnl / (self.entry_price * self.quantity)) * 100

    @property
    def notional_value(self) -> Decimal:
        """Current notional value of the position."""
        return self.current_price * self.quantity


class PaperOrder(BaseModel):
    """Represents a paper trading order."""

    order_id: str
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None  # For limit orders
    filled_quantity: Decimal = Decimal("0")
    filled_price: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    slippage: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")

    @field_validator("quantity", "filled_quantity", "filled_price", "slippage", "fees", mode="before")
    @classmethod
    def convert_to_decimal(cls, v) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @field_validator("price", mode="before")
    @classmethod
    def convert_price_to_decimal(cls, v) -> Optional[Decimal]:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @property
    def total_cost(self) -> Decimal:
        """Total cost including fees."""
        return self.filled_price * self.filled_quantity + self.fees


class PaperTrade(BaseModel):
    """Represents a completed paper trade."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fees: Decimal
    slippage: Decimal
    timestamp: datetime = Field(default_factory=datetime.now)
    pnl: Decimal = Decimal("0")  # Realized PnL (for closing trades)

    @field_validator("quantity", "price", "fees", "slippage", "pnl", mode="before")
    @classmethod
    def convert_to_decimal(cls, v) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class PerformanceMetrics(BaseModel):
    """Performance metrics for the paper trading account."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_percent: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    current_equity: Decimal = Decimal("0")
    initial_equity: Decimal = Decimal("0")

    # Time-series data for Sharpe calculation
    daily_returns: list = Field(default_factory=list)

    @field_validator(
        "total_pnl", "total_fees", "largest_win", "largest_loss",
        "max_drawdown", "max_drawdown_percent", "peak_equity",
        "current_equity", "initial_equity", mode="before"
    )
    @classmethod
    def convert_to_decimal(cls, v) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @property
    def win_rate(self) -> Decimal:
        """Win rate percentage."""
        if self.total_trades == 0:
            return Decimal("0")
        return Decimal(str(self.winning_trades)) / Decimal(str(self.total_trades)) * 100

    @property
    def average_win(self) -> Decimal:
        """Average winning trade size."""
        if self.winning_trades == 0:
            return Decimal("0")
        # This is approximate; for exact, we'd need to track all trades
        return self.largest_win / Decimal("2")  # Rough estimate

    @property
    def average_loss(self) -> Decimal:
        """Average losing trade size."""
        if self.losing_trades == 0:
            return Decimal("0")
        return self.largest_loss / Decimal("2")  # Rough estimate

    @property
    def profit_factor(self) -> Decimal:
        """Ratio of gross profit to gross loss."""
        if self.largest_loss == 0:
            return Decimal("999")  # Infinite profit factor
        gross_profit = self.largest_win * Decimal(str(self.winning_trades))
        gross_loss = abs(self.largest_loss) * Decimal(str(self.losing_trades))
        if gross_loss == 0:
            return Decimal("999")
        return gross_profit / gross_loss

    @property
    def return_percent(self) -> Decimal:
        """Total return as percentage of initial equity."""
        if self.initial_equity == 0:
            return Decimal("0")
        return (self.current_equity - self.initial_equity) / self.initial_equity * 100

    def calculate_sharpe_ratio(self, risk_free_rate: Decimal = Decimal("0.02")) -> Decimal:
        """
        Calculate annualized Sharpe ratio.

        Args:
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            Annualized Sharpe ratio
        """
        if len(self.daily_returns) < 2:
            return Decimal("0")

        import statistics
        returns = [float(r) for r in self.daily_returns]
        mean_return = Decimal(str(statistics.mean(returns)))
        std_return = Decimal(str(statistics.stdev(returns))) if len(returns) > 1 else Decimal("1")

        if std_return == 0:
            return Decimal("0")

        # Annualize (assuming 252 trading days)
        daily_rf = risk_free_rate / Decimal("252")
        excess_return = mean_return - daily_rf
        annualized_sharpe = (excess_return / std_return) * Decimal("15.87")  # sqrt(252)

        return annualized_sharpe.quantize(Decimal("0.01"))

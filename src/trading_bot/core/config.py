"""
Configuration management for the trading bot.
Uses pydantic-settings for validation and environment variable loading.
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """PostgreSQL database configuration."""

    host: str = Field(default="localhost", alias="POSTGRES_HOST")
    port: int = Field(default=5432, alias="POSTGRES_PORT")
    database: str = Field(default="trading_bot", alias="POSTGRES_DB")
    user: str = Field(default="trading_user", alias="POSTGRES_USER")
    password: str = Field(default="trading_password", alias="POSTGRES_PASSWORD")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def url(self) -> str:
        """Get PostgreSQL connection URL."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class RedisConfig(BaseSettings):
    """Redis configuration."""

    host: str = Field(default="localhost", alias="REDIS_HOST")
    port: int = Field(default=6379, alias="REDIS_PORT")
    db: int = Field(default=0, alias="REDIS_DB")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def url(self) -> str:
        """Get Redis connection URL."""
        return f"redis://{self.host}:{self.port}/{self.db}"


class BinanceConfig(BaseSettings):
    """Binance exchange configuration."""

    testnet_enabled: bool = Field(default=True, alias="BINANCE_TESTNET_ENABLED")
    api_key: str = Field(default="", alias="BINANCE_TESTNET_API_KEY")
    api_secret: str = Field(default="", alias="BINANCE_TESTNET_API_SECRET")

    # Testnet URLs
    testnet_base_url: str = "https://testnet.binance.vision/api"
    testnet_ws_url: str = "wss://testnet.binance.vision/ws"

    # Production URLs (not used by default)
    base_url: str = "https://api.binance.com/api"
    ws_url: str = "wss://stream.binance.com:9443/ws"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def active_base_url(self) -> str:
        """Get the active base URL based on testnet setting."""
        return self.testnet_base_url if self.testnet_enabled else self.base_url

    @property
    def active_ws_url(self) -> str:
        """Get the active WebSocket URL based on testnet setting."""
        return self.testnet_ws_url if self.testnet_enabled else self.ws_url


class TradingConfig(BaseSettings):
    """Trading parameters and risk management."""

    default_symbols: List[str] = Field(
        default=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        alias="DEFAULT_SYMBOLS"
    )
    orderbook_depth: int = Field(default=20, alias="ORDERBOOK_DEPTH")
    price_precision: int = Field(default=8, alias="PRICE_PRECISION")
    quantity_precision: int = Field(default=8, alias="QUANTITY_PRECISION")

    # Risk management
    max_position_size: float = Field(default=1000.0, alias="MAX_POSITION_SIZE")
    max_slippage_percent: float = Field(default=0.5, alias="MAX_SLIPPAGE_PERCENT")
    min_profit_percent: float = Field(default=0.3, alias="MIN_PROFIT_PERCENT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("default_symbols", mode="before")
    @classmethod
    def parse_symbols(cls, v: str | List[str]) -> List[str]:
        """Parse comma-separated symbols string into list."""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",")]
        return v


class AppConfig(BaseSettings):
    """Main application configuration."""

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    binance: BinanceConfig = Field(default_factory=BinanceConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)

    def __init__(self, **kwargs):  # type: ignore
        super().__init__(**kwargs)
        self.database = DatabaseConfig()
        self.redis = RedisConfig()
        self.binance = BinanceConfig()
        self.trading = TradingConfig()


# Global configuration instance
config = AppConfig()

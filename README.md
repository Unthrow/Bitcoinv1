# Crypto Trading Bot

A professional cryptocurrency trading bot designed to detect and exploit market inefficiencies through arbitrage and other strategies.

## Features

- **Real-time Order Book Monitoring**: Stream order book data from multiple exchanges via WebSocket
- **Async Architecture**: Built with Python asyncio for high-performance concurrent operations
- **Data Persistence**: Redis for fast caching, PostgreSQL for historical data
- **Type Safety**: Full type hints with Pydantic models for data validation
- **Modular Design**: Easy to add new exchanges and trading strategies
- **Backtesting Framework**: Test strategies against historical data
- **Docker Support**: Complete Docker Compose setup for local development

## Project Structure

```
Bitcoinv1/
├── src/
│   └── trading_bot/
│       ├── core/              # Core configuration and logging
│       ├── data/              # Data streaming and management
│       ├── models/            # Pydantic data models
│       ├── strategies/        # Trading strategies
│       ├── backtesting/       # Backtesting framework
│       ├── exchanges/         # Exchange connectors
│       └── utils/             # Utility functions
├── tests/                     # Unit and integration tests
├── config/                    # Configuration files
├── docker/                    # Docker configuration
├── scripts/                   # Utility scripts
├── logs/                      # Application logs
└── data_storage/              # Local data storage
```

## Prerequisites

- Python 3.11+
- Docker and Docker Compose (for local development)
- Binance Testnet API credentials (free)

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Bitcoinv1
```

### 2. Set Up Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and add your Binance Testnet credentials:

```env
BINANCE_TESTNET_API_KEY=your_api_key_here
BINANCE_TESTNET_API_SECRET=your_api_secret_here
```

Get free testnet credentials at: https://testnet.binance.vision/

### 3. Start with Docker Compose (Recommended)

```bash
# Start all services (Redis, PostgreSQL, Trading Bot)
docker-compose up -d

# View logs
docker-compose logs -f trading_bot

# Stop services
docker-compose down
```

### 4. Manual Setup (Alternative)

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Redis and PostgreSQL manually or via Docker
docker-compose up -d redis postgres

# Run the bot
python -m src.trading_bot.main
```

## Configuration

All configuration is managed through environment variables and the `src/trading_bot/core/config.py` file.

### Key Configuration Options

- `DEFAULT_SYMBOLS`: Trading pairs to monitor (default: BTCUSDT,ETHUSDT,BNBUSDT)
- `ORDERBOOK_DEPTH`: Order book depth to fetch (default: 20)
- `MIN_PROFIT_PERCENT`: Minimum profit threshold for arbitrage (default: 0.3%)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

## Usage Examples

### Stream Order Book Data

```python
import asyncio
from src.trading_bot.data import DataManager

async def main():
    async with DataManager() as dm:
        # Get latest order book
        orderbook = await dm.get_orderbook("BTCUSDT")
        print(f"Best bid: {orderbook.best_bid.price}")
        print(f"Best ask: {orderbook.best_ask.price}")
        print(f"Spread: {orderbook.spread}")

        # Subscribe to updates
        def on_update(ob):
            print(f"Updated: {ob.symbol} @ {ob.mid_price}")

        dm.subscribe("orderbook:BTCUSDT", on_update)

        # Keep running
        await asyncio.sleep(60)

asyncio.run(main())
```

### Access Historical Data

```python
import asyncio
from src.trading_bot.data import DataManager
import time

async def main():
    async with DataManager() as dm:
        # Get order books from the last hour
        end_time = int(time.time() * 1000)
        start_time = end_time - (60 * 60 * 1000)

        orderbooks = await dm.get_historical_orderbooks(
            "BTCUSDT",
            start_time,
            end_time,
            limit=100
        )

        print(f"Retrieved {len(orderbooks)} snapshots")

asyncio.run(main())
```

## Development

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### Code Quality Tools

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type check
mypy src/

# Run tests
pytest tests/ -v --cov=src/trading_bot
```

### Project Standards

- **Type Hints**: All functions must have type hints
- **Async/Await**: Use async patterns for I/O operations
- **Error Handling**: Proper exception handling with structured logging
- **Documentation**: Docstrings for all public functions and classes
- **Testing**: Unit tests for all critical components

## Database Schema

### Tables

- `orderbook_snapshots`: Order book snapshots over time
- `trades`: Executed trades
- `arbitrage_opportunities`: Detected arbitrage opportunities
- `executed_orders`: Order execution records
- `backtest_results`: Backtesting results

See `docker/init.sql` for complete schema.

## Architecture

### Core Components

1. **DataManager**: Orchestrates data streaming and storage
   - Manages WebSocket connections to exchanges
   - Handles data persistence (Redis + PostgreSQL)
   - Distributes data to subscribers

2. **BinanceClient**: Async Binance API client
   - REST API calls for account and market data
   - WebSocket streams for real-time updates
   - Automatic reconnection handling

3. **Models**: Pydantic models for type safety
   - OrderBook, Trade, Ticker
   - ArbitrageOpportunity
   - Validated with proper precision (Decimal)

## Roadmap

- [x] Project structure and core framework
- [x] Binance testnet integration
- [x] Real-time order book streaming
- [x] Data persistence (Redis + PostgreSQL)
- [ ] Simple arbitrage detector
- [ ] Multi-exchange support
- [ ] Backtesting framework
- [ ] Advanced trading strategies
- [ ] Risk management system
- [ ] Web dashboard for monitoring
- [ ] Production deployment setup

## Security

- Never commit `.env` files with real credentials
- Use testnet for development
- Implement proper API key rotation
- Monitor for unusual activity
- Use read-only API keys when possible

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## Support

For questions and issues, please open a GitHub issue.

## Disclaimer

This software is for educational purposes only. Use at your own risk. Cryptocurrency trading carries significant risk. Never risk more than you can afford to lose.

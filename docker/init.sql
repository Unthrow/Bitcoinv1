-- Initialize trading bot database

-- Create tables for order book data
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timestamp BIGINT NOT NULL,
    bids JSONB NOT NULL,
    asks JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_snapshot UNIQUE (exchange, symbol, timestamp)
);

CREATE INDEX idx_orderbook_symbol_time ON orderbook_snapshots(symbol, timestamp DESC);
CREATE INDEX idx_orderbook_exchange ON orderbook_snapshots(exchange);

-- Create tables for trades
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    trade_id VARCHAR(100),
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    side VARCHAR(10) NOT NULL,
    timestamp BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trades_symbol_time ON trades(symbol, timestamp DESC);
CREATE INDEX idx_trades_exchange ON trades(exchange);

-- Create tables for arbitrage opportunities
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    buy_exchange VARCHAR(50) NOT NULL,
    sell_exchange VARCHAR(50) NOT NULL,
    buy_price DECIMAL(20, 8) NOT NULL,
    sell_price DECIMAL(20, 8) NOT NULL,
    profit_percent DECIMAL(10, 4) NOT NULL,
    timestamp BIGINT NOT NULL,
    executed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_arbitrage_symbol ON arbitrage_opportunities(symbol);
CREATE INDEX idx_arbitrage_timestamp ON arbitrage_opportunities(timestamp DESC);
CREATE INDEX idx_arbitrage_executed ON arbitrage_opportunities(executed);

-- Create tables for executed orders
CREATE TABLE IF NOT EXISTS executed_orders (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    status VARCHAR(20) NOT NULL,
    timestamp BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_order UNIQUE (exchange, order_id)
);

CREATE INDEX idx_orders_symbol ON executed_orders(symbol);
CREATE INDEX idx_orders_status ON executed_orders(status);

-- Create tables for backtesting results
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    start_time BIGINT NOT NULL,
    end_time BIGINT NOT NULL,
    initial_capital DECIMAL(20, 8) NOT NULL,
    final_capital DECIMAL(20, 8) NOT NULL,
    total_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    losing_trades INTEGER NOT NULL,
    max_drawdown DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    profit_factor DECIMAL(10, 4),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backtest_strategy ON backtest_results(strategy_name);
CREATE INDEX idx_backtest_symbol ON backtest_results(symbol);

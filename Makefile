.PHONY: help install dev-install test lint format type-check clean docker-up docker-down docker-logs

help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make dev-install   - Install development dependencies"
	@echo "  make test          - Run tests with coverage"
	@echo "  make lint          - Run linter (ruff)"
	@echo "  make format        - Format code with black"
	@echo "  make type-check    - Run type checker (mypy)"
	@echo "  make clean         - Clean up cache and build files"
	@echo "  make docker-up     - Start all Docker services"
	@echo "  make docker-down   - Stop all Docker services"
	@echo "  make docker-logs   - View Docker logs"
	@echo "  make run           - Run the trading bot"
	@echo "  make example       - Run example usage script"

install:
	pip install -r requirements.txt

dev-install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=src/trading_bot --cov-report=term-missing

lint:
	ruff check src/ tests/

format:
	black src/ tests/ scripts/

type-check:
	mypy src/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .coverage htmlcov/ dist/ build/

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f trading_bot

run:
	python -m src.trading_bot.main

example:
	python scripts/example_usage.py

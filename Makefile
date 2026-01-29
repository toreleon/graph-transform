.PHONY: test lint build install clean help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage
	uv run pytest --cov=graph_transform --cov-report=term-missing

lint: ## Run linter (ruff)
	uv run ruff check src/ tests/

format: ## Format code (ruff)
	uv run ruff format src/ tests/

build: ## Build distribution packages
	uv build

install: ## Install in development mode
	uv sync --all-extras

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov

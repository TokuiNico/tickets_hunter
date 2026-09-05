# Developer shortcuts. Every target is a thin wrapper over `uv`, so the same
# commands work without make (see CONTRIBUTING.md).
.DEFAULT_GOAL := help
.PHONY: help install lock requirements lint format test e2e e2e-install check bench build run-settings run-bot clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv and install runtime + dev dependencies from uv.lock
	uv sync --frozen

lock: ## Re-resolve dependencies after editing pyproject.toml, then refresh requirement.txt
	uv lock
	$(MAKE) requirements

requirements: ## Regenerate requirement.txt (pip fallback) from uv.lock
	uv export --no-dev --no-hashes --no-emit-project --no-annotate --no-header -o requirement.txt

lint: ## Ruff lint + format check + emoji check (same as CI)
	uv run ruff check .
	uv run ruff format --check tests benchmarks
	uv run python scripts/check_no_emoji.py

format: ## Auto-fix lint issues and format tests/benchmarks
	uv run ruff check --fix .
	uv run ruff format tests benchmarks

test: ## Unit tests with coverage
	uv run pytest tests/unit --cov=src --cov-report=term-missing

e2e-install: ## Download the Playwright Chromium used by e2e tests
	uv run playwright install --with-deps chromium

e2e: ## End-to-end tests (real settings.py process + Chromium)
	uv run pytest tests/e2e

check: lint test ## Everything a PR must pass locally (excluding e2e)

bench: ## Pure-Python micro benchmarks (see benchmarks/README.md)
	uv run python benchmarks/bench_pure.py

build: ## Build Windows executables with PyInstaller (run on Windows)
	uv sync --frozen --no-dev --group build
	uv run pyinstaller build_scripts/nodriver_tixcraft.spec --clean --noconfirm
	uv run pyinstaller build_scripts/settings.spec --clean --noconfirm

run-settings: ## Start the settings web UI
	cd src && uv run python settings.py

run-bot: ## Start the bot with src/settings.json
	cd src && uv run python nodriver_tixcraft.py --input settings.json

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache .coverage coverage.xml htmlcov test-results build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

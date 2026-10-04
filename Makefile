# Ledgerline developer commands. Run `make help` for the list.
UV ?= uv
PY := backend/.venv/bin/python
.DEFAULT_GOAL := help

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install backend (venv) and frontend dependencies
	cd backend && $(UV) venv --python 3.12 .venv && $(UV) pip install --python .venv/bin/python -e ".[dev]"
	cd frontend && npm install

migrate: ## Apply database migrations (uses DB_URL from .env)
	cd backend && .venv/bin/alembic upgrade head

seed: ## Create the demo company, user and sample bills (offline extraction)
	cd backend && .venv/bin/python -m scripts.seed_demo

seed-live: ## Same as seed, but every sample goes through the real OpenAI provider
	cd backend && .venv/bin/python -m scripts.seed_demo --live

backend: ## Run the API on http://localhost:8000 (docs at /docs)
	cd backend && .venv/bin/uvicorn app.main:create_app --factory --reload --port 8000

frontend: ## Run the web app on http://localhost:5173
	cd frontend && npm run dev

test: ## Run backend and frontend tests
	cd backend && .venv/bin/pytest
	cd frontend && npm test

lint: ## Ruff, mypy, ESLint, Prettier and TypeScript checks
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
	cd frontend && npm run lint && npm run format:check && npm run typecheck

format: ## Auto-format backend and frontend
	cd backend && .venv/bin/ruff format . && .venv/bin/ruff check . --fix
	cd frontend && npm run format

.PHONY: help setup migrate seed seed-live backend frontend test lint format

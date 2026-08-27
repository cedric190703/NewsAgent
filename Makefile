# Convenience targets. Everything works without them; see README.md.
.DEFAULT_GOAL := help
VENV := backend/.venv
PY   := $(VENV)/bin/python

.PHONY: help install test lint fmt run-backend run-frontend demo docker clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Create the backend venv and install both sides
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r backend/requirements-dev.txt
	cd frontend && npm install

test: ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest

lint: ## Lint the backend and type-check the frontend
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run typecheck

fmt: ## Apply safe lint fixes
	cd backend && .venv/bin/ruff check --fix app tests

run-backend: ## Start the API on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload

run-frontend: ## Start the UI on :5173
	cd frontend && npm run dev

demo: ## Run one pipeline in the terminal, no model or API keys needed
	cd backend && LLM_PROVIDER=mock .venv/bin/python -m app.graph.harness \
		--theme "coral reef restoration" --providers mock --subtopics 2 --ephemeral

docker: ## Build and start the full stack
	docker compose up --build

clean: ## Remove caches and build output
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf backend/.pytest_cache backend/.ruff_cache frontend/dist

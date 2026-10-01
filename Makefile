.PHONY: help venv install test coverage lint format-check type-check check probe \
	docker-up docker-restart docker-logs docker-logs-all docker-status \
	docker-shell docker-pull docker-down docker-reset

PYTHON ?= python3.14
VENV ?= venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PY := $(BIN)/python
COMPOSE ?= docker compose
# Logger-name pattern for `make docker-logs` (case-insensitive regex)
FILTER ?= fansync

venv: ## Create the virtualenv
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: venv ## Install dev requirements into the virtualenv
	$(PIP) install -r requirements-dev.txt

test: ## Run all tests
	$(PY) -m pytest tests/ -v --tb=short

coverage: ## Run tests with a coverage report
	$(PY) -m pytest tests/ --cov=custom_components/fansync --cov-report=term-missing

lint: ## Run Ruff
	$(PY) -m ruff check .

format-check: ## Check Black formatting
	$(PY) -m black --check --line-length 100 --include '\.py$$' custom_components/ tests/

type-check: ## Run mypy
	$(PY) -m mypy custom_components/fansync --check-untyped-defs

check: coverage lint format-check type-check ## Run every check CI runs

probe: ## Measure how a real fan responds to raw writes (interactive); ARGS='--lights' for the light
	$(PY) scripts/probe_device.py $(ARGS)

# --- Local Home Assistant in Docker (see docker-compose.yml, dev-config/) ---

docker-up: ## Start the dev Home Assistant at http://localhost:8123
	$(COMPOSE) up -d
	@echo "Home Assistant: http://localhost:8123"

docker-restart: ## Restart the container to pick up code changes
	$(COMPOSE) restart

docker-logs: ## Follow records whose logger matches FILTER (default: fansync), e.g. FILTER='fansync|websockets'
	@# Matches the [logger] field only, case-insensitively, and keeps the continuation
	@# lines (tracebacks) of a matching record. --no-log-prefix drops the container name.
	$(COMPOSE) logs -f --no-log-prefix | awk -v pat='$(FILTER)' ' \
	  BEGIN { esc = sprintf("%c", 27); pat = tolower(pat) } \
	  { line = $$0; gsub(esc "\\[[0-9;]*m", "", line) } \
	  line ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] / { \
	    keep = 0; \
	    if (match(line, /\[[^]]+\]/)) keep = (tolower(substr(line, RSTART + 1, RLENGTH - 2)) ~ pat); \
	  } \
	  keep { print; fflush() }'

docker-logs-all: ## Follow the whole container log
	$(COMPOSE) logs -f

docker-status: ## Show container state and health
	$(COMPOSE) ps

docker-shell: ## Open a shell inside the container
	$(COMPOSE) exec homeassistant bash

docker-pull: ## Pull the image pinned in docker-compose.yml
	$(COMPOSE) pull

docker-down: ## Stop and remove the container, keeping its config volume
	$(COMPOSE) down

docker-reset: ## Delete the config volume and start fresh (wipes all HA data)
	$(COMPOSE) down -v
	$(COMPOSE) up -d
	@echo "Home Assistant: http://localhost:8123 (onboarding required again)"

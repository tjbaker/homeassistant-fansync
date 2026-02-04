.PHONY: venv install test coverage lint format-check type-check check

PYTHON ?= python3.13
VENV ?= venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PY := $(BIN)/python

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip

install: venv
	$(PIP) install -r requirements-dev.txt

test:
	$(PY) -m pytest tests/ -v --tb=short

coverage:
	$(PY) -m pytest tests/ --cov=custom_components/fansync --cov-report=term-missing

lint:
	$(PY) -m ruff check .

format-check:
	$(PY) -m black --check --line-length 100 --include '\.py$$' custom_components/ tests/

type-check:
	$(PY) -m mypy custom_components/fansync --check-untyped-defs

check: coverage lint format-check type-check

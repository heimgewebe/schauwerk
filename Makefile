.PHONY: lint compile-check test registry-validate validate

VENV_BIN := $(if $(wildcard .venv/bin/python),.venv/bin/,)
PYTHON ?= $(VENV_BIN)python
RUFF ?= $(VENV_BIN)ruff
PYTEST ?= $(VENV_BIN)pytest

lint:
	$(RUFF) check src tests

compile-check:
	$(PYTHON) -m compileall -q src

registry-validate:
	$(PYTHON) -m schauwerk.registry_validation

test:
	$(PYTEST)

validate: lint compile-check registry-validate test

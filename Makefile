.PHONY: python-version-check lint compile-check test registry-validate validate

SYSTEM_PYTHON := $(shell command -v python3.13 2>/dev/null || command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,$(SYSTEM_PYTHON))

export PYTHONPATH := $(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH),)

python-version-check:
	@if [ -z "$(PYTHON)" ]; then \
		echo "Schauwerk requires Python >=3.11,<3.14. Create .venv with Python 3.11-3.13 or set PYTHON=/path/to/python."; \
		exit 2; \
	fi
	@$(PYTHON) -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)' || { \
		echo "Schauwerk requires Python >=3.11,<3.14; selected interpreter: $$($(PYTHON) --version 2>&1). Create .venv with Python 3.11-3.13 or set PYTHON=/path/to/python."; \
		exit 2; \
	}

lint: python-version-check
	$(PYTHON) -m ruff check src scripts tests

compile-check: python-version-check
	$(PYTHON) -m compileall -q src

registry-validate: python-version-check
	$(PYTHON) -m schauwerk.registry_validation

test: python-version-check
	$(PYTHON) -m pytest

validate: lint compile-check registry-validate test

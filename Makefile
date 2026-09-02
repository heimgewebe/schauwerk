.PHONY: python-version-check lint compile-check test registry-validate validate

PYTHON_CANDIDATES := python3 python python3.13 python3.12 python3.11
ifeq ($(origin PYTHON), undefined)
ifneq ($(wildcard .venv/bin/python),)
PYTHON := .venv/bin/python
else
PYTHON := $(shell for candidate in $(PYTHON_CANDIDATES); do path=$$(command -v "$$candidate" 2>/dev/null) || continue; "$$path" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)' >/dev/null 2>&1 && { printf '%s\n' "$$candidate"; break; }; done)
endif
endif

export PYTHONPATH := $(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH),)

python-version-check:
	@if [ -z "$(PYTHON)" ]; then \
		echo "Schauwerk requires Python >=3.11,<3.14. No supported interpreter was found on PATH; create .venv with Python 3.11-3.13 or set PYTHON=/path/to/python."; \
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

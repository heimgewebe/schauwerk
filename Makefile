.PHONY: python-version-check lint compile-check test browser-smoke registry-validate validate

PYTHON_CANDIDATES := python3 python python3.13 python3.12 python3.11
BROWSER_SMOKE_TEST := test_canvas_import_browser_xml_validation_when_chrome_available
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

# The DOM/Chrome smoke test is browser-runtime coverage, not Python-version coverage.
# CI runs the Python suite without it on every supported interpreter and executes the
# smoke once on Python 3.12 with a fresh Chrome profile and one bounded retry.
test: python-version-check
	@if [ -n "$(CI)" ]; then \
		$(PYTHON) -m pytest -k 'not $(BROWSER_SMOKE_TEST)' || exit $$?; \
		if $(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then \
			$(MAKE) browser-smoke PYTHON="$(PYTHON)"; \
		fi; \
	else \
		$(PYTHON) -m pytest; \
	fi

browser-smoke: python-version-check
	$(PYTHON) scripts/run_browser_smoke.py

validate: lint compile-check registry-validate test

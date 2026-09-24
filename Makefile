.PHONY: python-version-check lint compile-check test browser-smoke registry-validate validate

PYTHON_CANDIDATES := python3 python python3.13 python3.12 python3.11
BROWSER_SMOKE_FILTER := test_canvas_import_browser_xml_validation_when_chrome_available or test_native_rebuild_failure_keeps_inconsistent_frame_inert_until_retry or test_native_viewer_browser_keeps_dragged_nodes_reachable_and_continues_pan_after_pinch or test_native_canvas_document_browser_drag_updates_edge_and_document_state or test_native_canvas_document_browser_preserves_absent_empty_arrays
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

# The DOM/Chrome smoke tests are browser-runtime coverage, not Python-version coverage.
# CI runs the Python suite without them on every supported interpreter and executes the
# smoke once on Python 3.12 with a fresh Chrome profile and one bounded retry.
test: python-version-check
	@if [ -n "$(CI)" ]; then \
		$(PYTHON) -m pytest -k 'not ($(BROWSER_SMOKE_FILTER))' || exit $$?; \
		if $(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then \
			$(MAKE) browser-smoke PYTHON="$(PYTHON)"; \
		fi; \
	else \
		$(PYTHON) -m pytest; \
	fi

browser-smoke: python-version-check
	$(PYTHON) scripts/run_browser_smoke.py

validate: lint compile-check registry-validate test

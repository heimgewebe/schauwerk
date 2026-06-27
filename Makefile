.PHONY: lint test registry-validate validate

lint:
	ruff check src tests

registry-validate:
	python -m schauwerk.registry_validation

test:
	pytest

validate: lint registry-validate test

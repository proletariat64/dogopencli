PYTHON ?= python3
DEV_PYTHON = .venv/bin/python

.PHONY: bootstrap test lint doc-guard test-doc-guard

bootstrap:
	$(PYTHON) -B scripts/bootstrap.py

test:
	$(DEV_PYTHON) -m pytest -q

lint:
	$(DEV_PYTHON) -m ruff check .
	$(DEV_PYTHON) -m ruff format --check .

doc-guard:
	$(PYTHON) -B scripts/doc_guard.py

test-doc-guard:
	$(PYTHON) -B -m unittest discover -s tests -p 'test_doc_guard.py' -v

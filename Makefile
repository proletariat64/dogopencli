PYTHON ?= python3
DEV_PYTHON = .venv/bin/python
BOOTSTRAP_DOMAIN ?= payment

.PHONY: bootstrap test lint doc-guard test-doc-guard

bootstrap:
	$(PYTHON) -B scripts/bootstrap.py
	rtk code-review-graph update --repo "$(CURDIR)" --brief
	$(DEV_PYTHON) -B scripts/bootstrap_browser.py --domain "$(BOOTSTRAP_DOMAIN)"

test:
	$(DEV_PYTHON) -m pytest -q --durations=20

lint:
	$(DEV_PYTHON) -m ruff check .
	$(DEV_PYTHON) -m ruff format --check .

doc-guard:
	$(PYTHON) -B scripts/doc_guard.py

test-doc-guard:
	$(PYTHON) -B -m unittest discover -s tests -p 'test_doc_guard.py' -v

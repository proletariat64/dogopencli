PYTHON ?= python3
DEV_PYTHON = .venv/bin/python
BOOTSTRAP_DOMAIN ?=

.PHONY: bootstrap test lint doc-guard test-doc-guard

bootstrap:
	$(PYTHON) -B scripts/bootstrap.py
	@if command -v rtk >/dev/null 2>&1; then \
		rtk code-review-graph update --repo "$(CURDIR)" --brief; \
	elif command -v code-review-graph >/dev/null 2>&1; then \
		code-review-graph update --repo "$(CURDIR)" --brief; \
	else \
		echo "error: rtk or code-review-graph is required" >&2; \
		exit 127; \
	fi
	$(DEV_PYTHON) -B scripts/bootstrap_browser.py $(if $(strip $(BOOTSTRAP_DOMAIN)),--domain "$(BOOTSTRAP_DOMAIN)")

test:
	$(DEV_PYTHON) -m pytest -q --durations=20

lint:
	$(DEV_PYTHON) -m ruff check .
	$(DEV_PYTHON) -m ruff format --check .

doc-guard:
	$(PYTHON) -B scripts/doc_guard.py

test-doc-guard:
	$(PYTHON) -B -m unittest discover -s tests -p 'test_doc_guard.py' -v

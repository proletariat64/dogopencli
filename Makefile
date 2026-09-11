PYTHON ?= python3

.PHONY: doc-guard test-doc-guard

doc-guard:
	$(PYTHON) -B scripts/doc_guard.py

test-doc-guard:
	$(PYTHON) -B -m unittest discover -s tests -p 'test_doc_guard.py' -v

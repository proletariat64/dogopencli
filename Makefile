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

# Independent delivery targets: CLI, registry program, and leaf packages.
TARGET ?= antcode
ANTCODE_PROJECT ?= pd.pt/dogopencli
DIST_DIR ?= dist
SITE_VERSION ?=
SITE_BUNDLE ?= dist/plugin-site/$(SITE_VERSION)
SITE_ROOT ?= /home/admin/workspace/plugin-site
SITE_PORT ?= 5910
PLUGIN ?=
PLUGIN_DIST ?= dist/plugin
PLUGIN_ZIP ?=
PLUGIN_VERSION ?=
PLUGIN_SITE ?=

.PHONY: check build smoke release publish-release release-site deploy-site release-plugin publish-plugin
check: doc-guard lint test

build:
	uv build --python "$(DEV_PYTHON)" --out-dir "$(DIST_DIR)"

smoke: build
	$(DEV_PYTHON) scripts/smoke_install.py --dist "$(DIST_DIR)"

release:
	VERSION="$(VERSION)" DRY_RUN="$(DRY_RUN)" RETRY="$(RETRY)" \
		$(DEV_PYTHON) scripts/release.py --target "$(TARGET)"

publish-release:
	$(DEV_PYTHON) scripts/publish_release.py --target "$(TARGET)" \
		--tag "$(TAG)" --dist "$(DIST_DIR)" \
		$(if $(filter antcode,$(TARGET)),--project "$(ANTCODE_PROJECT)")

release-site:
	$(DEV_PYTHON) -B tools/plugin-site/build.py --version "$(SITE_VERSION)" --output "$(SITE_BUNDLE)"

deploy-site:
	$(PYTHON) -B tools/plugin-site/deploy.py --bundle "$(SITE_BUNDLE)" --root "$(SITE_ROOT)" --port "$(SITE_PORT)"

release-plugin:
	@mkdir -p "$(dir $(PLUGIN_DIST))"
	$(DEV_PYTHON) tools/leaf-dev/leaf.py pack "$(PLUGIN)" --output "$(PLUGIN_DIST)"

publish-plugin:
	$(DEV_PYTHON) tools/plugin-site/publish.py --zip "$(PLUGIN_ZIP)" \
		--url "$(PLUGIN_SITE)" --version "$(PLUGIN_VERSION)" $(if $(filter 1,$(ALLOW_HTTP)),--allow-http)

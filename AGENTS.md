# Repository Guidelines

## Refactoring

- Every change must fit the new architecture and interface. Retire mismatched code; migrate required business behavior to new contracts.
- No users depend on old versions. Remove backward-compatibility aliases, shims, wrappers, and fallbacks.
- Use legacy code only for business-output cross-checks, in isolation. The new runtime must not import, wrap, or call it.
- Retrieve old Python source from GitHub release tags when needed. Delete obsolete code/tests/docs; keep no legacy copies in the repo.

## Scope and Architecture
Dogopencli is a Python CLI for querying the product operations platform, intended for one person on one machine. Four bundled pilot packages are available for explicit installation: payment.sla.baselines list/get, collection.cost list, liquidity.reference.entities list and fx.trade list. Each leaf owns its native contracts and is accepted independently. Historical inquiries are not current registrations; later implementation requires a bounded ticket and isolated pinned-release reference. Further migrations proceed through assigned bounded batch tickets. Read the leaf migration procedure before starting another batch. Other collection capabilities, including VA fees, pools and physical accounts, remain deferred.

Payment production scope starts at `https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/`. The current collection pilot covers the verified `collectionProductManagement/productPriceManagement/channelCost` transaction-cost inquiry. Historical SLA/VA rule entries are reference material for later explicitly scoped work, not current installed capabilities. Confirm actual menus and API contracts before implementation; historical knowledge-base designs do not prove current production behavior.

Liquidity uses the verified `https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt` entry and its allowlisted inquiry contracts; payment authorization does not establish liquidity access.

Keep every business operation inquiry-only. Allow explicitly verified query endpoints and request actions through a shared transport. HTTP method alone does not establish read-only behavior. Exclude mutation commands and arbitrary request or JavaScript entry points.

## Project Structure
The application uses the following layout:

- `src/dogopencli/`: CLI, configuration, browser transport, and plugin discovery.
- `src/dogopencli/contracts.py`: neutral endpoint, capability and parsed-result contracts.
- `src/dogopencli/domain_contracts.py`: side-effect-free domain identity and auth declarations.
- `src/dogopencli/leaf_packages/<domain>/<dotted-leaf>/`: bundled manifests and self-contained business adapters.
- `leaf_packages/<domain>/<dotted-leaf>/`: independent migration packages delivered as ZIPs, outside the host wheel.
- `src/dogopencli/leaves/`: package lifecycle, registry, shared runtime, documentation and temporary cache.
- `tests/`: unit and integration tests with sanitized fixtures.
- `docs/`: current contracts and development guides.

Keep native business queries in independent leaf packages; centralize authentication, request restrictions, pagination conventions, and error reporting.

## Browser and Configuration
Use headed Chrome for interactive OAuth/SSO login and headless Chrome for routine CDP queries. Reuse a dedicated profile with only one Chrome process owning it.

Never use CDP ports **9330–9340**, including tests and verification. Before browser or authentication work, read `~/dev/di/docs/spec/browser-cdp-v1.1.md` and its referenced implementation; adapt its defaults. Keep cookies, tokens, profiles, and sensitive responses out of Git and logs.

## Development and Testing
Prefix shell commands with `rtk`; use `rtk proxy <command>` for unsupported commands. Use the pytest and Ruff configuration in `pyproject.toml`:

- `rtk pytest -q`: run tests.
- `rtk proxy ruff check .`: lint Python.
- `rtk proxy ruff format --check .`: check formatting.

Use four-space indentation, type hints, `snake_case` functions/modules, and `PascalCase` classes. Name tests `test_*.py`. Cover request rejection, authentication expiry, pagination, and parsing with fake CDP responses; production validation must remain inquiry-only. No coverage threshold is established.

## Research and Contribution Workflow
Query `~/dev/dogpdkb/graphify_flatten_ready/` with `graphify query` or `graphify explain` first, then verify cited source documents. Read-only research must not rebuild graphs or save results.

Use code-review-graph first for code relationships and before nontrivial code edits. Before commits or reviews, refresh it and analyze changes against the actual default branch. Keep `.code-review-graph/` local.

Use conventional commit and PR prefixes such as `feat:`, `fix:`, and `docs:`. PRs should explain behavior, link relevant issues, report validation, and identify unverified production assumptions.

## Agent skills

### Issue tracker

Track issues and specs in GitHub Issues for
`proletariat64/dogopencli`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage labels.
See `docs/agents/triage-labels.md`.

### Domain docs

Maintain business terms in `CONTEXT.md` and current contracts in the responsible
guide. See `docs/agents/domain.md`; keep execution and version history out of
current development documents.

### Leaf development

For leaf development, packaging or migration, start with `tools/leaf-dev/README.md`
and read its relevant guides. The assigned batch ticket owns business scope.

# Repository Guidelines

## Scope and Architecture
Dogopencli is a Python CLI for querying the product operations platform, intended for one person on one machine. The current scope covers payment products, the collection transaction-cost inquiries in issue #21, SLA configuration inquiries in issue #27 and VA rule inquiries in issue #32. Other collection capabilities, including VA fees, pools and physical accounts, remain deferred.

Payment production scope starts at `https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/`. Collection scope covers the verified `collectionProductManagement/productPriceManagement/channelCost`, `collectionProductManagement/productSLAManagement/SlaManagement` and `collectionProductManagement/networkConstruction/VARuleManagement` entries and their cost/SLA/VA rule inquiry contracts. Confirm actual menus and API contracts before implementation; historical knowledge-base designs do not prove current production behavior.

Keep every business operation inquiry-only. Allow explicitly verified query endpoints and request actions through a shared transport. HTTP method alone does not establish read-only behavior. Exclude mutation commands and arbitrary request or JavaScript entry points.

## Project Structure
The application uses the following layout:

- `src/dogopencli/`: CLI, configuration, browser transport, and plugin discovery.
- `src/dogopencli/plugins/payment/`: payment queries, schemas, and response parsing.
- `src/dogopencli/plugins/collection/`: collection transaction-cost, SLA configuration and VA rule queries and schemas.
- `tests/`: unit and integration tests with sanitized fixtures.
- `docs/`: verified API contracts and design decisions.

Keep domain queries in plugins; centralize authentication, request restrictions, pagination conventions, and error reporting.

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

Use single-context domain documentation: root `CONTEXT.md`
and `docs/adr/`. See `docs/agents/domain.md`.

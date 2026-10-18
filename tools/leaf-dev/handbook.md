# Leaf plugin development handbook

Build ordinary List leaves with the host List SDK. Start from
[the executable sample](example/); use [interfaces](interfaces.md) for declarations.
For an assigned migration batch, also follow [the migration procedure](workflow.md).

## 1. Qualify the native inquiry

Query PDKB with `graphify`, verify its source documents, and inspect prior successful
UAT scopes before querying production. Historical inputs are starting points;
confirm the current native request and business response.

Record the read-only endpoint/action, browser entry, allowed request fields, scope,
paging mode, qualified widths, primary ID, total meaning and failure envelope.
Choose the native ID that identifies one returned record. Prefer a native field;
use a composite hash only for a reviewed composite identity without a suitable
single field. Keep amounts, types, nested objects and unknown fields unchanged.

**Done:** one explicit inquiry contract and an evidence-backed query scope.
Authentication or HTTP 200 alone does not establish a successful business query.

## 2. Declare SDK collection and implement native mapping

Copy [leaf.json](example/leaf.json) and [adapter.py](example/adapter.py).
Change their identity, endpoint, relation, scope, request builder, parser and prose
together. The sample's `.invalid` endpoint is synthetic; run it only in its tests.

- Manifest: declare `collection.provider`, `paging` and `primary_id`.
- Adapter: implement `capability`, `scope` and `filter`; add `get` only for a
  verified native detail inquiry.
- Capability: provide the restricted `EndpointContract`, `page_body` and native
  parser. See [the SDK adapter contract](interfaces.md#adapter).
- Host: owns `collect_list`, page loops, retries, quality evidence and publication.

Keep the standard leaf in one root adapter file. Resolve optional resources from
`Path(__file__).parent` inside methods; bare sibling imports have no package-loader
support. Installed adapters use host dependencies; installation installs no new
Python dependencies. Imports and construction must be free of side effects.

**Done:** a self-contained SDK declaration and native request/parser, with no
leaf-owned pagination or cache publisher. All four bundled pilots use this path.

## 3. Exercise the public CLI with fake responses

Run the sample exercise, then adapt the
[pilot tests](../../tests/integration/test_leaf_pilots_cli.py) to the new contract:

```bash
rtk proxy uv run python -m pytest -q tests/integration/test_leaf_handbook.py
```

Cover allowed/rejected requests, native values/types, paging, identity conflicts,
count gaps, business errors and auth expiry. Verify live makes no publication;
complete nonempty refresh and offline match; failed/empty/incomplete refresh
preserves the prior capture. Include filters and native get when declared.

**Done:** focused CLI checks and required repository tests/lint/doc/review gates pass.
Fake transport proves behavior, not production qualification.

## 4. Verify and pack one candidate

Use `leaf.py` from the repository root; output must be a new directory:

```bash
rtk proxy uv run python tools/leaf-dev/leaf.py verify /path/to/leaf
rtk proxy uv run python tools/leaf-dev/leaf.py pack /path/to/leaf --output /path/to/delivery
```

Install that ZIP through the public CLI into task-owned config. Source is separate
from the installed snapshot; changed source requires a new candidate. Static
verification checks package declarations, not business methods.

**Done:** immutable ZIP, `SHA256SUMS`, `delivery.json` and successful local installation.
For package boundaries, see [interfaces](interfaces.md#package).

## 5. Accept that candidate against production

Use one verified installed host, run outside the checkout, and use task-owned
config/cache/evidence. Coordinate one SSO/profile/CDP lifecycle; parallel inquiry
workers own separate query targets. Human SSO stays manual; preserve credentials.

For each declared action, obtain a genuine nonempty result using the qualified
scope. For List, compare live/refresh with their own native responses and offline
with its own refresh input: complete records, values, types, precision, ordering
and multiplicity. Counts alone do not establish equality. Use `leaf.py capture`
and `compare`; keep raw responses private. Identity/count conflicts or unexplained
differences block acceptance. Keep `--limit 0` for full output.

**Done:** exact-candidate inquiry evidence, native comparison and applicable
refresh/offline checks pass. [Migration delivery](workflow.md) defines HTTP smoke
and batch integration; [Duckdog import](duckdog-import.md) applies only to an
explicitly assigned supported import. Report tests, production UAT, CI and release
as separate results.

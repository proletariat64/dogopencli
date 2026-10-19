# Leaf plugin development handbook

Build ordinary List and native Get leaves with the host SDKs. Start from
the executable [List+Get](example/) or [Get-only](example-get-only/) sample;
use [interfaces](interfaces.md) for declarations and
[Get SDK](../../docs/agents/get-sdk.md) for detail/composition semantics.
For an assigned migration batch, also follow [the migration procedure](workflow.md).

## 1. Qualify the native inquiry

Start with the [leaf-relations helper](../../.agents/skills/leaf-relations/SKILL.md)
for a light PDKB/frontend/inquiry scan and scope-relative simple/complex proposal.
Human confirmation is required even at full confidence; complex relationships
also need scoped experiments and model confirmation. The helper returns a spec
and sample, then asks whether to continue development or end research. Continue
here only after that choice. Leaf-dev remains the development/acceptance flow.

Query PDKB with `graphify` and verify its source documents. Prior successful UAT
scopes are useful starting points when available, not required portable inputs;
small current inquiry-only calls can establish evidence. Confirm the current
native request and business response within the accepted scope.

Record the read-only endpoint/action, browser entry, allowed request fields, scope,
paging mode, qualified widths, primary ID, total meaning and failure envelope.
Choose the native ID that identifies one returned record. Prefer a native field;
use a composite hash only for a reviewed composite identity without a suitable
single field. Keep amounts, types, nested objects and unknown fields unchanged.

**Done:** one explicit inquiry contract and an evidence-backed query scope.
Authentication or HTTP 200 alone does not establish a successful business query.

## 2. Declare operations and implement native mapping

Copy [leaf.json](example/leaf.json) and [adapter.py](example/adapter.py).
Change their identity, endpoint, relation, scope, request builder, parser and prose
together. The sample's `.invalid` endpoint is synthetic; run it only in its tests.

- Manifest: declare `collection.provider`, `paging` and `primary_id`.
- List adapter: implement `capability`, `scope` and `filter`.
- Capability: provide the restricted `EndpointContract`, `page_body` and native
  parser. See [the SDK adapter contract](interfaces.md#adapter).
- Host: owns `collect_list`, page loops, retries, quality evidence and publication.

For Get, declare lookup meaning, returned identity and required context separately.
Implement `detail_capability(parameters)` with pure `request_body` and
`parse_detail` hooks; the host executes its independent restricted endpoint.
Get-only starts from [its own sample](example-get-only/) and needs no List methods,
`collection` or `dataset`. For a qualified List-to-Get association, declare
`list_binding`; standard `list --live --with-detail` returns each selected row
as `{record, detail}`. [Get SDK](../../docs/agents/get-sdk.md) owns binding rules,
windowing, projection, atomic failure and native-root coverage limits.

Keep the standard leaf in one root adapter file. Resolve optional resources from
`Path(__file__).parent` inside methods; bare sibling imports have no package-loader
support. Installed adapters use host dependencies; installation installs no new
Python dependencies. Imports and construction must be free of side effects.

**Done:** a self-contained SDK declaration and native request/parser, with no
leaf-owned querying, pagination or cache publisher.

## 3. Exercise the public CLI with fake responses

Run the sample exercise, then adapt the
[pilot tests](../../tests/integration/test_leaf_pilots_cli.py) to the new contract:

```bash
rtk proxy uv run python -m pytest -q tests/integration/test_leaf_handbook.py
```

Cover allowed/rejected requests, native values/types, paging, identity conflicts,
count gaps, business errors and auth expiry. Verify live makes no publication;
complete nonempty refresh and offline match; failed/empty/incomplete refresh
preserves the prior capture. For Get, verify independent lookup and required
context, native nested preservation, identity/scope failures and no cache writes.
For declared composition, test selected-window detail calls and all-or-failure
output through the same installed CLI. The samples are exercised as directories
and immutable ZIPs; their `.invalid` endpoints never run against a real browser.

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

For Get, compare the output to its own native Detail response, not a List row.
For `--live --with-detail`, compare `record` and `detail` to their respective
native sources, confirm selected-window detail calls and unchanged saved List
records/capture time. A valid root detail does not prove separate history or child
coverage. Get and composition are live-only and have no refresh/offline/import.

**Done:** exact-candidate inquiry evidence, native comparison and applicable
refresh/offline checks pass. [Migration delivery](workflow.md) defines HTTP smoke
and batch integration; [Duckdog import](duckdog-import.md) applies only to an
explicitly assigned supported import. Report tests, production UAT, CI and release
as separate results.

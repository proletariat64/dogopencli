# Leaf interfaces

Use the [handbook](handbook.md) for development steps and
[the sample](example/) for executable code. Runtime definitions are authoritative.

## Manifest

[The schema and validator](../../src/dogopencli/leaves/registry.py) define accepted
fields. Start from [leaf.json](example/leaf.json), then run `leaf.py verify`.

| Declaration | Meaning |
| --- | --- |
| `domain`, `name` | Known host domain and dotted leaf name; identity is `domain.name`. |
| `adapter` | Root Python file and exported object, e.g. `adapter.py:adapter`. |
| `operations` | Verified `list` and/or `get`, each with description and parameters. Host provides refresh/prune/describe/help. |
| `summary`, `purpose`, `fields` | Discovery and business field meanings; preserve unknown native fields in output. |
| `identity`, `identity_description` | Native record identity and its meaning; align List identity with the SDK declaration. |
| `limitations`, `examples` | Scope/interpretation limits and valid action-first commands. |
| `dataset.relation` | Unique SQL binding for List; omit for get-only. |
| `collection` | Host List SDK provider, native paging and primary ID; omit for get-only. |

A standard SDK List declares:

```json
{
  "collection": {
    "provider": "general",
    "paging": {"mode": "page_number", "page_sizes": [50]},
    "primary_id": {"type": "field", "fields": ["uniqueId"]}
  }
}
```

Replace these illustrative values with the endpoint's verified contract.
`page_sizes` is descending and endpoint-qualified. Paging modes are `page_number`,
`offset` (absolute zero-based rowStart) and `single` (one request). A field identity
has one native column; `hash` needs reviewed native columns and preserves native
JSON. Optional `latest_by` selects the newest conflicting row; conflicts still
leave coverage incomplete. Optional `max_pages` and `budget_seconds` narrow host
bounds. Provider `general` works in any domain; `<domain>.collection` is private
to its owner. Domain declarations do not register SDKs.

[The SDK contract](../../docs/agents/list-collection-sdk.md) owns provider isolation,
identity rules, unknown semantics, fallback and quality evidence.

Parameters require `name`, `type`, `required`, `description`. Types are string,
integer, number or boolean; optional defaults, choices and multiple values follow
the validator. CLI names use kebab-case; adapter keys use underscores. Host flags
are reserved. `required` governs acquisition; replay uses the saved scope.
`local_field` permits an explicit offline filter only when `filter` implements its
verified mapping; it does not filter automatically or extend saved coverage.

Help/describe/GUI prose comes from this manifest without activating adapters.
Reconcile desired GUI edits into source before reinstallation.

## Adapter

The [runtime](../../src/dogopencli/leaves/runtime.py) invokes these methods:

| Method | Responsibility |
| --- | --- |
| `capability(parameters)` | Validate inputs and return a native transport capability. No inquiry. |
| `scope(parameters)` | Stable string describing the native acquisition scope; canonical JSON suits structured inputs. |
| `filter(records, parameters)` | Supported local filters only; return unchanged records when none are supported. |
| `get(session, parameters, identity)` | Only for declared Get: issue the native detail request through the supplied session and validate its identity echo. |

For SDK List, the capability supplies:

| Member | Responsibility |
| --- | --- |
| `name`, `page_url` | Stable inquiry name and verified authenticated application entry. |
| `contract` | Actual host `EndpointContract`: endpoint, method/encoding, allowed/fixed keys, qualified widths and identity/total semantics. Nested inquiry JSON needs its own allowlist. |
| `page_body(scope, position, page_size)` | Build one native allowlisted request. Position is a page number or absolute offset according to `paging.mode`. |
| `parse_page(body)` | Numbered/single paging: validate native business status, rows and page metadata; return host `ParsedPage`. |
| `parse_rows(body)` | Offset paging: validate business status, rows and native total; return `(rows, total)`. |
| `validate_rows_scope(rows, scope)` | Optional native scope validation beyond a fixed `contract.scope_field`. |

Use neutral contracts from `dogopencli.contracts`. Primary identity comes from
`collection.primary_id`; SDK List needs neither `identity_key` nor `collector`.
The host calls `collect_list`, applies deadlines/retries/fallback, records quality,
and gates refresh publication. The leaf owns native meaning and mapping.

Authentication, business-envelope and schema failures are hard failures. Keep
native fields/types/decimals intact; do not convert a failure into empty success.
Get remains a native detail inquiry, separate from List row lookup.

An endpoint requiring custom acquisition or unresolved semantics needs a bounded
ticket and explicit tests; consult the SDK contract first. Existing packages
without `collection` require their own `collector`; this is not the standard
SDK development path.

## Package

Package root contains `leaf.json`, its declared root adapter and optional ordinary
resources/README. ZIP entries start at this root, with no enclosing wrapper.
Installed identity comes from the manifest. Keep configuration, credentials,
profiles, caches, bytecode, datasets, symlinks and generated output outside it.
[The package validator](../../src/dogopencli/leaves/package.py) owns content/size limits.

Installation imports and checks adapter signatures without querying business data;
it initializes empty List storage or validates retained bindings. Static verify/pack and help
are declaration-only. Uninstall retains Duckdog data; query/refresh do not import
it. A valid ZIP is not evidence of working runtime methods or production data.

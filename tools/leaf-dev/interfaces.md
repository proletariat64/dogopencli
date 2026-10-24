# Leaf interfaces

Use the [handbook](handbook.md) for development steps and
the [List+Get sample](example/) or [Get-only sample](example-get-only/) for
executable code. Runtime definitions are authoritative.

## Manifest

[The schema and validator](../../src/dogopencli/leaves/registry.py) define accepted
fields. Start from [leaf.json](example/leaf.json), then run `leaf.py verify`.

| Declaration | Meaning |
| --- | --- |
| `domain`, `name` | Known host domain and dotted leaf name; identity is `domain.name`. |
| `adapter` | Root Python file and exported object, e.g. `adapter.py:adapter`. |
| `operations` | Verified `list` and/or `get`, each with description and parameters. Host provides describe/help, plus refresh/prune for List. |
| `operations.<action>.execution` | `standard` (also the omission convention) or explicit `custom`; chosen independently for List/Get. |
| Custom operation `queries`, `max_requests`, `budget_seconds` | Named List/detail inquiries and shared execution bounds; see [Custom query SDK](../../docs/agents/custom-query-sdk.md). |
| `summary`, `purpose`, `fields` | Discovery and business field meanings; preserve unknown native fields in output. |
| `identity`, `identity_description` | Native List identity and its meaning; Get-only may use an empty List identity. |
| `operations.get.lookup`, `result_identity` | Positional lookup meaning and independently declared returned identity. Use literal top-level `fields` or exact object-key `paths`, never both; include descriptions. |
| `operations.get.result_shape` | Optional `object` (default) or native `array`; array identities describe members, and a qualified empty array stays empty. |
| `operations.get.list_binding` | Optional qualified same-value List field/context mapping enabling `--live --with-detail` for object Gets; array Gets cannot bind to List records. |
| `limitations`, `examples` | Scope/interpretation limits and valid action-first commands. |
| `dataset.relation` | Unique SQL binding for List; omit for get-only. |
| `collection` | Standard List SDK provider, primary ID and exactly one of native `paging` or flat `sources`; omit for get-only and custom List. |

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
`offset` (absolute zero-based rowStart), `single` (one request with a native total)
and `single_response` (one separately qualified response without a native total).
`single_response` requires one width and verified identity. For a genuinely
unpaged endpoint, use `page_sizes: [0]` with `EndpointContract.page_size=0` and
omit pagination fields from the native request; zero is not a capacity limit.
Other modes require positive widths. Use
[its sample](example-single-response/). A field identity
has one native column; `hash` needs reviewed native columns and preserves native
JSON. Optional `latest_by` selects the newest conflicting row; conflicts still
leave coverage incomplete. Optional `max_pages` and `budget_seconds` narrow host
bounds. Provider `general` works in any domain; `<domain>.collection` is private
to its owner. Domain declarations do not register SDKs.

A reviewed hash identity may set `primary_id.allow_empty_components: true` when
explicit native null/empty values are meaningful business dimensions. The typed
tuple preserves null, empty strings and zero distinctly; missing fields and
object/array components still fail. Default identity validation stays strict.
Public List identity validation and saved replay apply the same opt-in only to
the declared hash components. No synthetic native ID or substituted value is added.

Optional `paging.termination: "short_page"` opts numbered/offset acquisition into
stable-hole recovery and two consecutive successful empty large batches as the
stop rule. Totals do not control progress. Require stable cross-width positions,
verified identity and positive qualified widths; local probes use only smaller
widths explicitly permitted by the endpoint contract. Normal fixed-width final
short pages remain valid; interior deficiencies need qualified local probes.
A pure optional `pagination_hole(error)` classifier may identify verified
record-specific business errors; other failures remain hard errors. Successful
bypasses are complete/exit 0 with a notice. The host retains five scoped query
records and revalidates only the latest record's holes and neighboring identities.
Omission or `"native_total"` keeps the existing rule; single modes cannot opt in.
Numbered parsers retain exact page/size echoes and may return `None` for total
fields; offset parsers may return `(rows, None)`. Evidence keeps null total and
`qualified_short_page`; see the [full SDK contract](../../docs/agents/list-collection-sdk.md)
and [VA capacity package](../../leaf_packages/collection/va.capacity/).

For an accepted multi-source model, replace top-level `paging` with a nonempty
`sources` map. Each source declares only its own `paging` and `primary_id`;
the provider and overall execution bounds are shared. Keep top-level
`primary_id` for the assembled root. No nested source sets or inferred join:
see [the executable sources sample](example-sources/).

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
| `capability(parameters)` | Single-source List: validate inputs and return a native transport capability. No inquiry. |
| `source_capability(name, parameters)` | Declared multi-source List: return that source's independent restricted capability. No inquiry. |
| `source_scope(name, parameters)` | Declared multi-source List: exact stable native scope for that source. |
| `assemble(records_by_source, parameters)` | Pure leaf-owned mapping of all complete sources to reviewed aggregate roots; no queries. |
| `scope(parameters)` | Stable string describing the native acquisition scope; canonical JSON suits structured inputs. |
| `filter(records, parameters)` | Supported local filters only; return unchanged records when none are supported. |
| `detail_capability(parameters)` | For standard Get: independent endpoint and pure native request/parser hooks. No inquiry. |
| `query_capability(operation, name, parameters)` | Custom operation: pure capability for one declared named inquiry. |
| `query_list(parameters, tools)` | Custom List: Python orchestration returning `CustomListResult` with records and business coverage. |
| `query_get(parameters, identity, tools)` | Custom Get: Python orchestration returning its declared public root. |

For SDK List, the capability supplies:

| Member | Responsibility |
| --- | --- |
| `name`, `page_url` | Stable inquiry name and verified authenticated application entry. |
| `contract` | Actual host `EndpointContract`: endpoint, method/encoding, allowed/fixed keys, qualified widths and identity/total semantics. Nested inquiry JSON needs its own allowlist. |
| `page_body(scope, position, page_size)` | Build one native allowlisted request. Position is a page number or absolute offset according to `paging.mode`. |
| `parse_page(body)` | Numbered/single paging: validate native business status, rows and page metadata; return host `ParsedPage`. |
| `parse_rows(body)` | Offset paging returns `(rows, native_total)`; qualified `single_response` returns `(rows, None)`. Validate native business status and shape in both. |
| `parse_metadata(body)` | Optional pure hook returning a native JSON object separate from rows; see [native page metadata](../../docs/agents/list-collection-sdk.md#native-page-metadata) for page association and cache semantics. |
| `validate_rows_scope(rows, scope)` | Optional native scope validation beyond a fixed `contract.scope_field`. |

Use neutral contracts from `dogopencli.contracts`. Primary identity comes from
`collection.primary_id`; SDK List needs neither `identity_key` nor `collector`.
The host calls `collect_list`, applies deadlines/retries/fallback, records quality,
and gates refresh publication. With declared `sources`, the host calls
`collect_sources`, sharing one deadline/page budget and invoking `assemble` only
after every required source is complete. Sources retain separate scopes and
acquisition evidence through cache replay; aggregate `reported_total` remains null.
The leaf owns native meaning and mapping.

Authentication, business-envelope and schema failures are hard failures. Keep
native fields/types/decimals intact; do not convert a failure into empty success.
Get remains a native detail inquiry, independent of List. Its capability supplies
`name`, `page_url`, `contract`, `request_body(parameters, identity)` and
`parse_detail(body, parameters, identity)`. The parser validates native business
status, declared native object/array shape, returned identity and scope before
returning the native value unchanged. Nested identity paths resolve exact object
keys; they neither flatten the result nor establish a business relationship.
Hooks receive no session/transport. Standard Get-only requires only `detail_capability`;
List methods apply only when List is declared.

[Get SDK](../../docs/agents/get-sdk.md) owns the exact declaration/binding,
live-only execution, native-root coverage and `{record, detail}` output rules.

For dependent inquiries or accepted custom orchestration, follow
[Custom query SDK](../../docs/agents/custom-query-sdk.md) for explicit operation
declarations, named tools, execution bounds and coverage. Unresolved business
semantics still require scoped qualification before implementation. Every standard
List requires `collection`; custom List declares named host tools instead.
Transport-taking adapter collectors are unsupported.

## Package

Package root contains `leaf.json`, its declared root adapter and optional ordinary
resources/README. ZIP entries start at this root, with no enclosing wrapper.
Installed identity comes from the manifest. Keep configuration, credentials,
profiles, caches, bytecode, datasets, symlinks and generated output outside it.
[The package validator](../../src/dogopencli/leaves/package.py) owns content/size limits.

Installation imports and checks adapter signatures without querying business data;
List installation initializes empty storage or validates retained bindings;
Get-only initializes no List storage. Static verify/pack and help
are declaration-only. Uninstall retains Duckdog data; query/refresh do not import
it. A valid ZIP is not evidence of working runtime methods or production data.

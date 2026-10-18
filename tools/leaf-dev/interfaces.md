# Leaf interfaces

Current manifest and adapter contracts. Start with the [handbook](handbook.md)
for a runnable example and development steps. Runtime definitions linked below
remain authoritative.

## Manifest

The runtime schema and semantic checks are in
[validate_manifest](../../src/dogopencli/leaves/registry.py). Do not maintain a copied
validator in a helper or a new documentation loader. Use a bundled manifest as a
starting point and run static verify after editing.

| Declaration | Contract |
| --- | --- |
| `domain`, `name` | Known host domain and dotted leaf name; global identity is `domain.name`. Installed folder and declaration must agree. |
| `adapter` | Local root Python filename and exported attribute, for example `adapter.py:adapter`. |
| `operations` | Nonempty declarations for `list` and/or `get`, each with `description` and `parameters`. Do not declare host maintenance/help actions as business operations. |
| `summary`, `purpose` | Short discovery summary and business purpose. |
| `fields` | Field name, type and meaning, optionally unit; field names are unique. This explains fields without projecting away unknown native fields. |
| `identity`, `identity_description` | Proven native identity fields and their meaning; document unknown identity explicitly rather than inventing one. |
| `limitations` | Query bounds, unresolved semantics and interpretation limits. |
| `examples` | Objects containing a title and current action-first command. |
| `dataset.relation` | Required for list leaves; a unique SQL relation binding. Get-only leaves must omit dataset. |

The [sample manifest](example/leaf.json) is the complete,
executable starting point. Change identity, relation, operations and business prose
alongside its adapter; do not invent a new manifest schema for each leaf.

Parameter declarations require `name`, `type`, `required` and `description`.
Supported types are string, integer, number and boolean; optional declarations
include default, choices, multiple and local_field. Names use kebab-case CLI flags;
adapter parameter keys use underscores. Boolean values are explicit true/false
(or 1/0), not implicit toggle flags. Host controls such as format, live, limit,
fields and completeness/freshness flags are reserved.

Use `required` for acquisition requirements; offline replay must remain possible
without resupplying the saved scope. A declared `local_field` permits an explicit
offline filter through the runtime gate; the adapter's filter still implements the
verified selection. It does not automatically filter records or prove coverage.
Reject unsupported offline scope expansion and document native filter semantics.

Progressive help is assembled once from the current command model, including
bounded discovery diagnostics. JSON serializes that document; one deterministic
text renderer formats it. Text uses the terminal's actual width, or 88 columns
when redirected or when terminal sizing is unavailable. It has no color, paging
or extra output flags. Help never activates adapters or initializes runtime state.

Parameter `argument_contract.modes` describes the current operation: list has
cache/live modes, refresh has refresh, and get has get. A nonempty `local_field`
permits an explicit cached-list filter; other business parameters are unavailable
for cache filtering. Acquisition modes retain manifest requirements and repeated
values. Host controls describe their current roles; accepted controls are not
marked unavailable merely because their policy has no effect in a given mode.

Help `errors` is the declared set of known host/runtime errors, not an exhaustive
list of arbitrary adapter failures. Consumers must handle unknown error codes.
Shared operation rules distinguish cached list, live acquisition, get, prune and
describe; correcting documentation does not change execution or exit codes.

Help, describe and GUI-editable prose come from this manifest. README is optional
supporting documentation. GUI saves update only the installed manifest, not your
source or original ZIP. Before deliberate reinstallation, reconcile any desired
installed documentation edits into the maintained source.

## Adapter

Export the object named by `adapter`. Follow the
[LeafAdapter protocol](../../src/dogopencli/leaves/adapter.py) and the
[common runtime](../../src/dogopencli/leaves/runtime.py):

| Method | Required for | Responsibility |
| --- | --- | --- |
| `capability(parameters)` | list or get | Return the verified TransportCapability; validate query values without making requests. |
| `scope(parameters)` | list | Return the stable string describing the native acquisition scope; canonical JSON is useful for structured scope. |
| `collector(capability, transport, scope, *, progress=None)` | legacy list without `collection` | Leaf-owned acquisition when no SDK declaration exists. Opted-in Lists do not implement this loop. |
| `filter(records, parameters)` | list | Apply only supported offline filters to saved records. No requests or storage writes. |
| `get(session, parameters, identity)` | get | Perform the verified native detail inquiry through the supplied session and return a business object. |

### Opt in to the common List collection API

For a standard List, declare `collection` in the manifest: `provider` (`general` or the owning domain's private `<domain>.collection`), `paging.mode` (`offset`, `page_number`, `single`), ordered verified `page_sizes`, and `primary_id` (`field` or SHA-256 `hash` of reviewed native columns). Optional `latest_by` selects the newest conflicting native row; otherwise last arrival wins, with incomplete coverage evidence. The host calls `collect_list` automatically; no `collector` method is needed. Page-width learning is kept in a separate local runtime-state file; no provider version field or Domain SDK registration exists. Read [the contract](../../docs/spec/list-collection-sdk.md).

### Bridge the adapter to the shared collector

`LeafAdapter` is only the entry interface. A newly written list also needs its own
native contract and parser. Import `EndpointContract` and `ParsedPage` from
`dogopencli.contracts`; keep business behavior in the installed leaf.
For the standard `collect_scope` path, define these in the adapter as the sample
does:

| Capability member | Required behavior |
| --- | --- |
| `name` | Stable capability identity for the request boundary. |
| `contract` | An actual host `EndpointContract` dataclass: method, host, path, encoding, allowed body keys, page size/base and proven identity/total assumptions. The runtime fingerprints this dataclass. |
| `page_url` | Verified authenticated application entry. It is distinct from API host/path; omitting it falls back to the payment entry. Supply the right entry for non-default applications. |
| `page_body(scope, position, page_size)` | Build only the allowed native request. `position` is `rowStart` for offset mode or native page number for numbered mode. `fixed_body_values` and nested JSON limits pin verified values/widths. |
| `parse_page(body)` or `parse_rows(body)` | Page-number/single mode returns `ParsedPage`; offset mode returns `(rows, total)`. Validate the native envelope and keep exact decimal values. |
| `identity_key(record)` | Return the proven hashable native identity used for collection consistency checks; agree with the manifest identity. |

These are the members exercised by the sample/common collection path. The
[common collector](../../src/dogopencli/collect.py) constructs requests, applies
bounded HTTP handling and validates paging/count/identity consistency. The parser
still owns business-envelope interpretation: HTTP 200 can contain a failure, and
missing rows are not automatically an empty result. Its `CollectedScope` carries
coverage evidence to the shared runtime. Do not return a bare record list from a
collector or set complete=true merely because parsing succeeded.

Use a specialized collector only when the endpoint's verified behavior requires
it. Consult payment for native get/filtering, liquidity for its response/offset
contracts, and FX for explicit unknown identity/total handling. These are separate
cases to test, not options to copy into every simple leaf. Current interfaces are
the development contract; this guide introduces no SDK or compatibility-version
framework.

Keep module import and object construction free of browser/network/storage effects:
installation imports adapter code and checks callable signatures, without invoking
its inquiry methods. Static verify/pack and declaration-only help/list do not
import it. Installation is local validation, not a sandbox or production UAT.

The host owns domain/auth gates, browser session, transport restrictions, common
result/error rendering, record-identity validation, acquisition quality policy,
cache publication, registry and Duckdog bindings. Return native business records
and acquisition evidence; do not write a second CLI, login path, cache publisher,
registry or dataset importer inside the adapter. Shared transport must reject
unverified requests. Preserve authentication expiry and business-failure errors as
failures, rather than converting them to usable incomplete or empty results.

A list leaf receives host refresh/prune; all leaves receive describe. Commands keep
the same action-first grammar: `dogopencli collection list sample.records`.

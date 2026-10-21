# Get SDK

Use the host Get SDK for one verified native detail endpoint. Follow the
[leaf handbook](../../tools/leaf-dev/handbook.md) for qualification and delivery;
[interfaces](../../tools/leaf-dev/interfaces.md) and the executable
[List+Get](../../tools/leaf-dev/example/) and
[Get-only](../../tools/leaf-dev/example-get-only/) samples show declarations and
pure native mappings. The synthetic endpoints run only in
[the installed CLI harness](../../tests/integration/test_leaf_handbook.py).

## Declare identities and context

`operations.get` declares `description`, `parameters`, `lookup` and
`result_identity`. `lookup.name` names the positional string's business meaning;
`lookup.description` explains how to obtain it. `result_identity.fields` names
literal top-level native identity keys, with a separate description. These
may differ from each other and from the top-level List `identity`.

For nested identity, use mutually exclusive `result_identity.paths`, for example
`{"paths": [["quotationDetail", "quotationId"]], "description": "Native quotation ID"}`.
Each path is a nonempty list of exact object keys. Keys containing dots remain
literal; there is no wildcard, index, expression or automatic traversal of arrays.
Every resolved identity component must be a nonblank string or an integer,
excluding booleans. Missing, null and non-scalar identities fail before projection.
The leaf still validates the identity's actual lookup echo and requested context.

An explicitly custom object Get may use the separately approved
`result_identity.request_fields` contract for a request-scoped aggregate whose
native root has no ID. See [Custom query SDK](custom-query-sdk.md). The composite
key belongs to the request metadata; it is not injected into the native response.
Standard Get continues to require native identity. Request-scoped Gets cannot
bind to List or declare an array root.

`operations.get.result_shape` defaults to `"object"`. An explicitly qualified
`"array"` Get returns the native root array without wrapping, deduplication or
latest-version selection. Declare identity over each member object; ambiguous or
duplicate identity tuples fail. A native successful `[]` remains `[]`; missing,
null or malformed containers fail. Array Gets cannot declare `list_binding`.

```json
{
  "get": {
    "description": "Read one native detail.",
    "parameters": [],
    "lookup": {"name": "recordId", "description": "Value from native List id."},
    "result_identity": {"fields": ["id"], "description": "Returned record ID."},
    "list_binding": {"identity_field": "id"}
  }
}
```

Declare required account/date/tenant context as ordinary Get parameters; fixed
native context belongs in the endpoint contract. The Get-only sample demonstrates
a business reference plus required account, returning a distinct numeric ID. It
has only `detail_capability`: omit List methods, `collection` and `dataset`.

The optional `list_binding` enables standard composition only after qualification.
Its `identity_field` names one unprojected native List field. Optional `parameters`
maps Get parameter names in manifest kebab-case to native List fields, for example
`{"account-id": "accountId"}`. Map every required Get context without a declared
default; unmapped defaults retain their declared values.
Values must already have the declared input type; the host converts native string
or integer lookup IDs to the CLI string representation. This is a same-value
binding, not a transformation or relation language. Having both operations alone
does not enable composition. New relationships or scope changes go through
[leaf-relations](../../.agents/skills/leaf-relations/SKILL.md) and human confirmation.

## Implement pure native mappings

`adapter.detail_capability(parameters)` returns an independent capability with
`name`, `page_url` and an actual `EndpointContract`. It exposes:

- `request_body(parameters, identity) -> dict`: construct the allowed native input.
- `parse_detail(body, parameters, identity) -> dict | list[dict]`: validate business
  status, the declared root shape, returned identity and requested scope; return
  the native root unchanged.

Neither hook receives a session or transport. The host owns browser/session
lifecycle, restricted GET/query, POST JSON or POST form execution, deadlines,
transient retries and auth reporting. A retry repeats this endpoint; a parser
never acquires children or history from another endpoint. Imports and constructors
are side-effect-free. There is no session-taking adapter `get` hook.

Validate before projection. Preserve native JSON types, precise decimals, nested
objects, arrays and unknown fields. A leaf may recognize a verified native
integer/string identity representation while retaining the response's type.
The host checks declared identity presence; the leaf validates its actual meaning
and input/echo relationship. Do not synthesize an ID or fall back to a List row.
Only verified native absence maps to `NOT_FOUND`; missing keys, null, an empty
object or business rejection follow that endpoint's qualified semantics and must
not become empty success. Auth, timeout, business, schema and identity failures
remain failures.

## Query and interpret coverage

Direct Get is action-first and inherently live:

```bash
dogopencli collection get sample.records one
dogopencli collection get sample.detail REF-one --account account-one
```

It needs no prior List or saved snapshot. It returns the declared native root
object or array. `--fields` projects the object's top-level fields, or each array
member's fields, after validation; array order and member count stay unchanged.
Get has no List paging. Empty or blank lookup input fails before authentication.
Metadata
records `query.identity` separately from `query.parameters`, `source`, `leaf`,
`operation`, `fetched_at`, `returned_count` (one object or actual array length),
`detail_scope: native_root` and
`detail_coverage`. Success proves acquisition of that native response, not complete
business-object expansion. Separate histories, logs and child pages are unqueried;
Get does not report List totals or unconditional dataset completeness.

Supported Lists expose only the singular `--with-detail`, requiring `--live`:

```bash
dogopencli collection list sample.records --live --with-detail --offset 1 --limit 1
```

The host acquires List under its existing quality policy, applies supported local
filters, then selects offset/limit once. It fetches detail only for that window,
preserving List order and multiplicity. `--limit 0` means all remaining matching
rows within execution bounds; an empty window makes no detail calls. Output is:

```json
[{"record": {"id": "two", "amount": "2.00"}, "detail": {"id": "two", "children": []}}]
```

Each member preserves its own native view. `--fields` selects native fields inside
`record` after binding; `detail` stays complete as returned. Neither object is
flattened or overwritten. Invalid binding, any detail failure or budget exhaustion
fails the whole query with affected-row context and no successful partial array.
Successful Gets preserve List acquisition evidence; they cannot upgrade an
incomplete List or prove coverage of unqueried children. Direct Get and composition
publish no temporary query cache or Duckdog dataset and preserve saved Lists.
Default/cached List, refresh, direct Get and unsupported leaves reject
`--with-detail` before business queries. Ordinary List behavior is unchanged.

Help/describe explain these declarations without inputs, adapter activation,
storage initialization or login. Verify/pack remain static; installation checks
adapter signatures without querying. Get-only installation creates no List store.

## Verify at the installed CLI boundary

Use directory and immutable ZIP installs with fake native transport. Exercise
independent Get, required context, differing input/echo names, values/types,
business/shape/identity/auth failures and cache preservation. For composition,
check selected-window request counts, zero/empty windows, ordering, projection,
failure after an earlier successful detail and unchanged List quality evidence.
Help is a side-effect check. Synthetic success is separate from production UAT:
compare direct Detail and each combined member to its own captured native source,
using the exact installed host and leaf ZIPs. Reuse `leaf.py` and plugin-helper;
there is no separate SDK distribution or packer.

For arrays, cover nonempty/empty roots, invalid members, duplicate native identity,
projection and unchanged cache. For nested identities, cover missing paths,
non-object parents, null/boolean/non-scalar values, literal dotted keys and
preservation of every sibling. Help/describe must expose shape and identity paths
without activating adapters or querying business data.

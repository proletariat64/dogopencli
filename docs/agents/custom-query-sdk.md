# Custom query SDK

Use custom execution when an accepted leaf scope needs dependent inquiries or
Python orchestration, such as collecting a directory before requesting each
record's detail. Ordinary single-source List, independent flat sources and one
native Get use the [List](list-collection-sdk.md) and [Get](get-sdk.md) SDKs.
`general` names a collection provider; `custom` selects an operation's execution
mode. They are separate choices.

The [registry](../../src/dogopencli/leaves/registry.py),
[query tools](../../src/dogopencli/leaves/query.py) and
[runtime](../../src/dogopencli/leaves/runtime.py) are authoritative. Follow the
[handbook](../../tools/leaf-dev/handbook.md) for qualification and delivery.

## Declare each operation

Set `operations.list.execution` or `operations.get.execution` to `"custom"`.
Omission means the existing standard contract; method presence never selects
custom execution. List and Get choose independently, including mixed modes.

A custom operation retains its ordinary `description` and `parameters`, and
requires a nonempty `queries` map, `max_requests` from 1 through 10000, and
`budget_seconds` from 1 through 1800. Query names use lowercase letters, digits
and underscores, beginning with a letter. Its operation and query objects reject
undeclared fields.

```json
{
  "operations": {
    "list": {
      "description": "Read an account directory and its details.",
      "parameters": [],
      "execution": "custom",
      "max_requests": 500,
      "budget_seconds": 300,
      "queries": {
        "accounts": {
          "kind": "list",
          "collection": {
            "provider": "general",
            "paging": {"mode": "offset", "page_sizes": [100, 10]},
            "primary_id": {"type": "field", "fields": ["alias"]}
          }
        },
        "detail": {
          "kind": "detail",
          "result_identity": {
            "fields": ["alias"],
            "description": "Native account alias."
          }
        }
      }
    }
  }
}
```

This excerpt illustrates the contract, not a qualified production endpoint.
A custom List still declares the leaf's `dataset`, public `identity` and fields;
omit top-level `collection`. Each named List query declares a single collection
policy with `provider`, `paging` and `primary_id`. Optional `latest_by`,
`max_pages` and `budget_seconds` retain the standard limits and meaning; nested
`sources` are unsupported. Paging, verified widths, identity and provider-domain
rules are the same as standard List, including qualified short-page and
single-response modes.

A named detail query declares `result_identity` using exactly one of `fields` or
`paths`, with a nonempty description. Optional `result_shape` is `object`
(default) or `array`. These follow the Get SDK's native identity and shape rules.
A custom public Get separately requires its public `lookup` and `result_identity`;
its returned root is checked against those public declarations. An accepted
object Get may also declare the existing same-value `list_binding`.
Standard operations reject custom `queries` and shared-budget fields.

## Implement Python orchestration

The adapter exposes pure
`query_capability(operation, name, parameters)` for each declared query. It
returns the same restricted native List or detail capability used by standard
SDKs: actual `EndpointContract`, `name`, `page_url`, request builder and parser.
The host resolves these declarations and checks hooks before browser acquisition.
Capability construction, imports and constructors remain free of side effects.

Custom entry points are:

| Entry | Result |
| --- | --- |
| `query_list(parameters, tools)` | `CustomListResult(records, evidence)` from `dogopencli.leaves.query`; evidence is `AcquisitionEvidence` from `dogopencli.result_policy`. |
| `query_get(parameters, identity, tools)` | Declared public root object or array. |
| `scope(parameters)` | Stable native scope string; required for every List. |
| `filter(records, parameters)` | Qualified local filtering; required for every List. |

The host passes `QueryTools`, with two inquiry methods:

- `collect(name, scope="")` returns a standard `CollectedScope`, including records
  and acquisition evidence. It uses that query's declared provider and policy;
  pagination, stable-hole handling and source learning stay in the host.
- `detail(name, identity, parameters=None)` returns a validated native object or
  array. Identity is a nonblank string. Omitted parameters use the operation's
  parameters; an explicit object supplies per-record native context. The parser
  still validates lookup echo and scope.

The host opens transport lazily and reuses one transport per declared query name
within the operation, so a detail loop can reuse its query target. All opened
transports close on successful finish, context exit, failure or cancellation.
`InquirySession` continues to own authentication and session lifecycle; the leaf
receives only the query tools.

Use ordinary Python to decide the inquiry sequence and combine records. Query
names are closed declarations, not an orchestration language. A query must be
called through the matching method. Leaf code receives no supported arbitrary
HTTP, JavaScript, session, transport or authentication entry point. These are
contracts for trusted local Python adapters, not a Python security sandbox.

## Enforce bounds and failures

The host shares one deadline and actual HTTP request allowance across all named
queries in an operation. Retries, pagination probes and repeated detail calls
consume the same allowance. A named List's local limits may narrow that shared
bound. Budget exhaustion is a failure.

For custom Get used through `list --live --with-detail`, the selected output
window shares one Get deadline and request allowance. The List SDK's window,
projection and whole-command failure rules still apply; that allowance is not
reset for each row. Direct Get remains live-only and does not publish business
cache or Duckdog data.

Authentication, network, timeout, business, malformed-response and identity
failures remain failures. The host remembers tool failures so catching an error
inside the adapter cannot turn it into successful partial output.

The sole qualified exception is an individual detail refusal: a detail parser
may raise `QueryRefused(native_code=...)` only after establishing this endpoint's
verified per-record refusal semantics. A custom List may catch that exception,
retain the account and mark its detail refused, with both completeness flags
false. Other business failures, including unqualified codes, remain hard errors.
Raising this exception from request construction or transport is a hard failure.
Custom Get cannot finish with refused or incomplete required inquiries.

## Preserve coverage and native values

The leaf owns output grain, source relationships, identity echoes, field
precedence, raw business objects, conflicts and coverage accounting. The host
does not infer joins or require every declared query to run: conditional Python
branches are allowed, so leaf tests and evidence must prove required coverage.

For List, return records and `AcquisitionEvidence` describing that exact output.
Retain each source's independent coverage and required/attempted/succeeded/refused
detail counts. An assembled root count cannot substitute for source coverage.
`collected_total` must equal the number of returned records. Incomplete collected
sources or retained detail refusals cannot be upgraded to complete output.

The host appends a `custom_query` trace to List `evidence.attempts`; direct custom
Get exposes `query_evidence` metadata. These record query calls, requests,
success/refusal/error status and collected-source evidence. Use stable, safe scope
and evidence values; credentials and raw production responses stay private.
If a custom operation fails with a `CliError`, its error metadata retains the
same `query_evidence` so completed source acquisition and the failed query remain
diagnosable without publishing partial records.

Normal List result policy controls live, strict, refresh and offline behavior.
Incomplete live results retain their evidence; strict rejects incomplete results,
and incomplete refresh preserves the prior published capture. Custom execution
does not add an independent cache or publication path.

## Verify the installed boundary

Static verify/pack checks declarations without importing the adapter. Installation
imports it and binds entry signatures without executing business methods.
Help/describe remain declaration-only. Test dependent calls and native
preservation through the installed CLI, including mixed List/Get modes,
shared budgets with retries/probes, retained qualified refusal, hard failure
after an earlier success, completeness contradictions and cache preservation.

`liquidity.cash.accounts` is a custom List case: cash directory, account baseline
and dependent account detail remain internal inquiries, preserving native nested
records in the combined directory. This does not register public baseline/Get
leaves or qualify `cash.balances`; the latter remains deferred. Fake responses
prove runtime behavior. Production acceptance requires the exact installed host
and package, full source and relationship coverage, and private native comparison
evidence under the assigned ticket.

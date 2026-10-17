# Leaf handbook: pilot evidence and development gaps

Observed: 2026-10-17
Scope: general
Status: snapshot

## Evidence boundary

Inspected the four tracked pilot packages and their immediate host dependencies at
`5407aad64b7df4aa08c90c7e28efaffbb22b22c7`, together with the current handbook.
Code-review-graph was consulted first; its indexed branch/head matched master
(284 source/test files, 644 test nodes). Targeted reads resolved runtime details.
This is source research, not a complete supported-leaf inventory or new production
UAT. The handbook's effectiveness needs an executable from-scratch development
exercise; successful installation of existing pilots alone cannot establish it.

## What the pilots actually demonstrate

| Pilot | Actual implementation chain | Complexity relevant to a handbook |
| --- | --- | --- |
| collection.cost | [adapter](../../src/dogopencli/leaf_packages/collection/cost/adapter.py) imports [CollectionCostCapability](../../src/dogopencli/plugins/collection/cost.py), which imports the [shared cost parser](../../src/dogopencli/plugins/cost.py); delegates to collect_scope. | Smallest adapter, but deliberately fixed to one 1000-row request; exceeding coverage is incomplete, never speculative paging. The parser accepts a verified omitted empty-list shape. It is a wrapper example, not a standalone new endpoint implementation. |
| payment.sla.baselines | [adapter](../../src/dogopencli/leaf_packages/payment/sla.baselines/adapter.py) imports [SLA list/detail capabilities and parser](../../src/dogopencli/plugins/payment/sla.py), uses collect_scope and execute_bounded. | List/get, canonical server-filter scope, explicit local-field mapping; bizLegalEntity is live-only. Omitted list is accepted only for zero total; null detail has its own not-found meaning. |
| liquidity.reference.entities | [adapter](../../src/dogopencli/leaf_packages/liquidity/reference.entities/adapter.py) wraps [REFERENCE_ENTITIES](../../src/dogopencli/plugins/liquidity/leaves.py) in [LiquidityListCapability](../../src/dogopencli/plugins/liquidity/capability.py), calling [collect_liquidity_scope](../../src/dogopencli/plugins/liquidity/collect.py). | Uses ordinary rowStart offset collection, with the shared native envelope/parser. Crucially overrides descriptor identity from id to instId. No leaf-local special collector, but depends on a broad legacy descriptor/collector implementation. |
| fx.trade | [adapter](../../src/dogopencli/leaf_packages/fx/trade/adapter.py) imports [FX_TRADE/query_request](../../src/dogopencli/plugins/fx/trade.py); implements its own acquire loop. | Explicit page/time budgets, stable reported-total checks, duplicate-content detection without invented identity. Identity and total semantics remain unknown, hence incomplete even when arrival count matches; cached filters are refused. Not the simple-leaf tutorial. |

The four packages each contain exactly `leaf.json` and `adapter.py` in tracked
source. None demonstrates a package-local auxiliary module or resource file.
Their imports demonstrate host-module dependencies, not portable multi-module
plugin loading. A resource-loading claim needs its own installed-snapshot test;
a sibling-module design should wait for an actual case and isolated import test.

The [pilot CLI tests](../../tests/integration/test_leaf_pilots_cli.py) exercise
native payment list/detail, the instId-only liquidity record, collection capacity
limits and FX unknown semantics through fake CDP. These are valuable preserved
behavior examples, not fresh production evidence.

## Missing bridge from a new endpoint to a working simple leaf

The handbook before this exercise explained adapter methods and package lifecycle,
but its manifest example had no complete runnable adapter. Copying the pilot
adapter requires existing host business modules. A from-scratch route needs:

1. A complete local capability and parser, with no import from the old leaf's
   business implementation. Host transport, collection and error utilities remain
   reusable. Keep the endpoint contract and parser in the root adapter for the
   first simple example; there is no need to invent an SDK or module loader.
2. Explain [EndpointContract and ParsedPage](../../src/dogopencli/plugins/__init__.py).
   For the common [collect_scope](../../src/dogopencli/collect.py) path, implement
   page_body(scope, page_num, page_size), parse_page(bytes), and identity_key(row),
   plus name/contract. Do not imply every legacy Capability protocol member is
   consumed by this runtime. Runtime fingerprints the dataclass endpoint contract.
3. Make the verified envelope and empty/business-failure behavior explicit in the
   parser. Preserve native row types, unknown fields and null/empty distinctions.
   Collection owns common coverage accounting; custom collectors must return
   honest CollectedScope/AcquisitionEvidence, not merely a list of records.
4. Explain page_url when a capability needs a domain-specific authenticated entry.
   [Runtime](../../src/dogopencli/leaves/runtime.py) passes it to
   [inquiry_session](../../src/dogopencli/inquiry.py); a missing URL falls back
   to the default payment entry. Endpoint host and browser startup URL are
   separate declarations. Do not infer cross-domain authentication from packaging.
5. Provide a runnable synthetic exercise through public CLI, fake CDP and isolated
   real storage: install, help/describe, live, refresh, offline equality, rejected
   failure preservation, and uninstall. Assert the native request and untouched
   unexpected fields; otherwise a trivial adapter returning constants could pass.
6. State the exercise's limit: it validates development instructions and host
   integration, while each real rewritten inquiry still needs its own scoped
   production comparison and UAT.

## How to evaluate the proposed migration approach

The owner's six suggestions are inputs to test, not findings from this bounded
inspection. Rewriting against current interfaces is feasible in principle because
native contracts/parsers can live in an adapter and shared transport/collection
already exist. These pilots do not yet prove that every supported leaf fits that
simple route or that old business modules can already be deleted.

Use measured properties to choose simple candidates: one verified endpoint,
straightforward envelope/identity, common paging, no custom multi-request assembly,
no backend-workaround collector and no required auxiliary modules. Adapter line
count alone is not a sufficient ranking. Determine order from a later supported
leaf inventory; this snapshot makes no candidate selection.

Freshly collecting replacement data can avoid compatibility conversion. It does
not change the installed-plugin uninstall contract: [ADR 0022](../adr/0022-installed-leaf-pilots.md)
retains Duckdog data. If migration-owned old data is only a comparison fixture,
record its exact ownership and disposal gate separately after comparison/UAT and
new synchronization; do not implement blanket deletion as part of uninstall.
Deleting legacy source likewise requires a resolved import/consumer check because
all four pilots currently depend on it. Preserve the business-output contract and
necessary knowledge, not accidental module dependencies or historical row counts.

## Executable standard-leaf validation

The follow-up exercise added [a complete synthetic leaf](../../examples/leaf_simple/)
with its own manifest, EndpointContract, page_body, identity_key and parse_page,
wrapped by the current LeafAdapter interface. It imports shared host utilities but
no legacy domain business implementation. Its endpoint and browser entry use
`leaf-handbook.invalid`; this is deliberately not a production capability or new
bundled leaf.

The [public CLI exercise](../../tests/integration/test_leaf_handbook.py) drives
the installed code through the existing fake CDP boundary. Real filesystem,
SQLite, DuckDB, request allowlisting, collection, quality policy and rendering are
used. The integration harness blocks sockets and process creation; raw production
records and authentication are unnecessary.

Observed run: `20` handbook cases and `4` existing pilot cases passed together
(`24 passed`). Directory and ZIP delivery exercise static verify, pack/reverify,
install, declaration help/describe/list, two-page acquisition, exact decimal and
unknown nested-field preservation, live without publication, full refresh despite
display limits, offline equality and idempotent uninstall. Empty/business/shape/
identity/strict-completeness/auth failures preserve prior cache rows and capture
time. Query/refresh leaves the initialized Duckdog table empty. An extra request
field is rejected before any business fetch.

Auxiliary-file probes establish narrower facts than generic package support:

- A directory package reading a static resource relative to `__file__` still works
  after the original source directory is deleted. This proves installed-snapshot
  resource lookup for that pattern; it does not prove arbitrary module loading.
- A directory package with a bare import of a unique sibling Python module passes
  static validation but fails installation with INVALID_LEAF and no published leaf.
  No sys.path mutation or package loader was added to make the test pass.

The handbook now links executable code rather than an incomplete manifest alone,
explains the capability/parser bridge and authenticated page_url, and supplies the
commands to repeat the exercise. This establishes a working standard paginated
list development path. It does not establish production endpoint correctness,
get/filter/custom-collector parity for a new leaf, a complete migration ranking,
or a legacy-data disposal plan. Those remain explicit per-leaf work.


An independent reader also completed all eight manual verify/pack/install/help/
describe/uninstall steps with the repository Python environment in a task-owned
temporary directory, then removed that test scope. No blocking gap was found for
the stated fixed-scope standard-list path. A suggested integer-ceiling calculation
was applied to the sample parser and the 24-case suite was rerun successfully.

This companion evidence file lives beside the maintained handbook so its linked
validation remains reviewable; the repository ignores new private research files.

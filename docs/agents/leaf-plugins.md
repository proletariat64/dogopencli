# Leaf plugin development handbook

Use this guide when authoring, packaging or migrating a dogopencli business leaf.
The [leaf ADR](../adr/0022-installed-leaf-pilots.md) defines the architecture;
[spec #239](https://github.com/proletariat64/dogopencli/issues/239) defines portable
installation. This handbook explains the current implementation and development
workflow. Domain terminology comes from [CONTEXT.md](../../CONTEXT.md).

The primary path below is a standard list leaf: one verified endpoint, a known
native identity, fixed total semantics and ordinary pagination, without backend
workarounds or multi-request assembly. The executable
[sample package](../../examples/leaf_simple/) and
[public CLI exercise](../../tests/integration/test_leaf_handbook.py) establish this
path. The [pilot research](leaf-handbook-evidence.md)
explains which parts the four pilots actually demonstrate. Neither a synthetic
exercise nor earlier pilot success qualifies a new production endpoint.

## Walk through a complete simple leaf

Read [leaf.json](../../examples/leaf_simple/leaf.json) and
[adapter.py](../../examples/leaf_simple/adapter.py) together. This example owns its
endpoint contract and response parser; it imports only shared host utilities, not
an existing business leaf. It is a development reference, not a fifth bundled leaf.

Its **synthetic** endpoint contract is deliberately explicit:

| Contract item | Example rule |
| --- | --- |
| Browser entry / endpoint | `https://leaf-handbook.invalid/app` / POST `/records/query`; test-only, never a verified production service. |
| Request | `scope=all`, zero-based `pageNo`, `pageSize=2`; no other fields. |
| Response | Boolean `success`, object-array `rows`, integer `pageNo`, `pageSize`, `total`. |
| Identity / total | Nonempty string `id`, unique records; fixed total counts those identities. |
| Empty / error | Successful empty is `rows=[]`, `total=0`; `success=false` is a business failure. |
| Coverage | Two pages for three records; shared collector verifies page echoes, totals and duplicate consistency. |
| Values | Preserve native fields, decimal text, exact JSON decimals and unknown nested fields. |

From the repository root, install development dependencies and execute the exercise:

```bash
uv sync --extra dev
uv run python -m pytest -q tests/integration/test_leaf_handbook.py
```

The tests use the real CLI, registry, collector, result policy, SQLite and DuckDB.
Only browser/CDP responses are fake; socket connections and process launches are
blocked by the integration harness. They verify directory/ZIP delivery, help,
request payloads, full records, live without publication, refresh/offline equality,
failure preservation and uninstall. They also probe resource loading and unsupported
bare sibling imports. No browser, login or production query is needed.

For a manual static/package walkthrough, use a new temporary directory:

```bash
leaf_work=$(mktemp -d)
cp -R examples/leaf_simple "$leaf_work/source"
uv run python .agents/skills/plugin-helper/scripts/plugin_helper.py verify "$leaf_work/source"
uv run python .agents/skills/plugin-helper/scripts/plugin_helper.py pack "$leaf_work/source" --output "$leaf_work/sample.zip"
uv run python .agents/skills/plugin-helper/scripts/plugin_helper.py verify "$leaf_work/sample.zip"
uv run dogopencli domain enable collection --config-dir "$leaf_work/config"
uv run dogopencli plugins install "$leaf_work/sample.zip" --config-dir "$leaf_work/config"
uv run dogopencli collection list sample.records -h --format text --config-dir "$leaf_work/config"
uv run dogopencli collection describe sample.records --format text --config-dir "$leaf_work/config"
uv run dogopencli plugins uninstall collection.sample.records --config-dir "$leaf_work/config"
```

Run the sample's live/refresh commands only through the offline test harness above.
To develop a real leaf, rewrite the manifest, contract, parser and tests from its
verified business knowledge. Replace the synthetic entry/endpoint and every
assumption in the table with evidence for that leaf. Complete the steps below
before production UAT. Passing installation alone checks method signatures, not
whether request/parsing methods produce correct business results.

## 1. Establish the inquiry contract

Choose one verified inquiry and its host domain. Record its native endpoint/action,
request scope, pagination/capacity, business identity, raw field types, detail
behavior and completeness limitations. Verify that each request is inquiry-only;
HTTP method alone does not establish this. Preserve native values and unknown
fields. Do not invent stable identities, totals or completeness to satisfy a schema.

For a later migration, first resume the paused
[migration map](https://github.com/proletariat64/dogopencli/issues/241) explicitly
and establish the supported-leaf inventory and consumer list. Create a bounded
per-leaf ticket stating the historical behavior,
new dotted identity, supported list/get operations, dependencies, verification scope
and eventual deletion candidates. Unsupported/deferred inquiries require their own
qualification decision; copying their implementation is not qualification.

Finish this step with an explicit request/result contract and a retained comparison
reference, not just a list of old source files.

## 2. Start from a working leaf

Current bundled sources live under [leaf_packages](../../src/dogopencli/leaf_packages/):

| Example | What to study |
| --- | --- |
| [collection/cost](../../src/dogopencli/leaf_packages/collection/cost/) | Small list-only adapter and single-request capacity evidence. |
| [payment/sla.baselines](../../src/dogopencli/leaf_packages/payment/sla.baselines/) | List/get, server scope and supported offline filters. |
| [liquidity/reference.entities](../../src/dogopencli/leaf_packages/liquidity/reference.entities/) | Reference records using the shared collection contract. |
| [fx/trade](../../src/dogopencli/leaf_packages/fx/trade/) | Bounded parameters and honest incomplete-result limitations. |

Independent migration packages are maintained under
`leaf_packages/<domain>/<dotted-name>/` at the repository root and delivered as
separate ZIPs. This keeps them outside automatic bundled-pilot discovery and the
host wheel. Their package README files receive the same title and link checks
as other repository documentation. Batch B01 evidence is recorded in
[migration B01](migration-b01-evidence.md).

Develop in a source directory separate from the installed snapshot. A package has
exactly one root layout:

```text
my-leaf/
├── leaf.json
├── adapter.py
├── README.md       # optional, independent prose
└── resources/      # optional ordinary auxiliary files/directories
```

The adapter filename is declared by the manifest; it must be a root Python file.
ZIP entries start directly with this content, not an enclosing `my-leaf/` wrapper.
Source directory and ZIP names do not define identity. The installer chooses the
standard domain/dotted-name destination from the manifest.

Packages must not contain configuration, credentials, browser profiles, caches,
business datasets, symlinks, unsafe paths or nested leaf manifests. Keep bytecode,
virtual environments and generated output outside the source. Current limits are
50 MiB per ZIP, 100 MiB expanded content and 1000 materialized entries. The
[shared validator](../../src/dogopencli/leaves/package.py) is authoritative; the
helper rejects invalid contents rather than silently making a distributable package
from private/runtime state.

Packages execute Python in the host environment. There is no dependency installation
or build phase. Each pilot owns its native endpoint contract, request construction,
parser and business collection policy. Shared host imports use side-effect-free
contracts and generic transport, collection, evidence and serialization utilities.
The host does not register or import a second business runtime.
All four pilots currently consist of a manifest and one adapter; none is evidence
for multi-module package loading. The handbook test separately installs a resource
variant, deletes its source directory, and successfully reads the installed
resource relative to `Path(__file__).parent`. This proves that resource path pattern
for the tested directory package. Read resources inside the relevant method, not
at module import while installation is staging the package.

The same test suite verifies that an uninstalled sibling module referenced by a
bare import passes static package checks but fails runtime installation. The loader
does not add the leaf directory to sys.path or give the adapter ordinary package
semantics. Keep the standard example in one adapter file; record real multi-module
or auxiliary-loader requirements in the relevant complex leaf's ticket and test
them from an installed snapshot. Do not infer support from ZIP accepting files or
from source-tree imports succeeding.

## 3. Declare the manifest

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

The [sample manifest](../../examples/leaf_simple/leaf.json) is the complete,
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
See the [help cleanup record](help-cleanup.md) for the replacement boundary and
compatibility verification.

Help, describe and GUI-editable prose come from this manifest. README is optional
supporting documentation. GUI saves update only the installed manifest, not your
source or original ZIP. Before deliberate reinstallation, reconcile any desired
installed documentation edits into the maintained source.

## 4. Implement the adapter

Export the object named by `adapter`. Follow the
[LeafAdapter protocol](../../src/dogopencli/leaves/adapter.py) and the
[common runtime](../../src/dogopencli/leaves/runtime.py):

| Method | Required for | Responsibility |
| --- | --- | --- |
| `capability(parameters)` | list or get | Return the verified TransportCapability; validate query values without making requests. |
| `scope(parameters)` | list | Return the stable string describing the native acquisition scope; canonical JSON is useful for structured scope. |
| `collector(capability, transport, scope, *, progress=None)` | list | Collect through the supplied restricted transport and return CollectedScope with truthful coverage evidence. Reuse collect_scope where suitable. |
| `filter(records, parameters)` | list | Apply only supported offline filters to saved records. No requests or storage writes. |
| `get(session, parameters, identity)` | get | Perform the verified native detail inquiry through the supplied session and return a business object. |

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
| `page_body(scope, page_num, page_size)` | Build only the allowed native request, rejecting unsupported scope or widths. `fixed_body_values` pins verified invariant values. |
| `parse_page(body)` | Validate the native success/error envelope, record shape, identity fields and pagination numbers; return `ParsedPage(records, page_num, page_size, total_count, total_pages)`. Use the host JSON parser to preserve exact decimal values. |
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

## 5. Verify, package and install in isolation

From the repository root, with the project environment installed:

```bash
uv run python .agents/skills/plugin-helper/scripts/plugin_helper.py verify /path/to/my-leaf
uv run python .agents/skills/plugin-helper/scripts/plugin_helper.py pack /path/to/my-leaf --output /path/to/delivery.zip
uv run python .agents/skills/plugin-helper/scripts/plugin_helper.py verify /path/to/delivery.zip
```

The output parent directory must exist; output must be outside the source and must
not already exist. The [plugin-helper skill](../../.agents/skills/plugin-helper/SKILL.md)
uses the host static validator, validates before and after packing, and preserves
source/existing output on failure. Passing it proves package validity, not adapter
runtime or production correctness. There is no `plugins pack` CLI command.

Use a dedicated configuration directory for local lifecycle checks:

```bash
dogopencli domain enable collection --config-dir /path/to/task-config
dogopencli plugins install /path/to/delivery.zip --config-dir /path/to/task-config
dogopencli plugins list --config-dir /path/to/task-config --format text
dogopencli collection list sample.records -h --config-dir /path/to/task-config --format text
dogopencli collection describe sample.records --config-dir /path/to/task-config --format text
dogopencli plugins uninstall collection.sample.records --config-dir /path/to/task-config
```

Use your manifest's actual identity throughout. Unknown/disabled domains reject
install. Duplicate identities fail without overwrite; to retest a changed source,
explicitly uninstall then install into the task configuration. No update/replace
or version comparison exists. Install checks the adapter interface and storage
bindings but makes no business inquiry. It initializes an empty list table or
validates a retained one. Uninstall clears owned temporary cache and retains
Duckdog rows/binding history; incompatible retained tables are diagnosed, not
silently repaired. Development source is not the installed snapshot.

HTTP(S) ZIP and explicit `bundled:<identity>` installation use the same package and
lifecycle contract. Downloads fail without automatic retry/resume and clean their
temporary artifacts; limits include a 60-second total deadline and at most five
redirects. Adding a new bundled leaf also requires distribution-resource and
outside-checkout wheel checks; local packaging alone does not add a bundled entry.

## 6. Prove behavior through the public CLI

Prefer the existing `run_cli` fixture with fake CDP responses and isolated real
temporary storage. Good tests assert externally visible records, quality metadata,
exit/error behavior and cache/dataset preservation. Avoid tests that only call a
private parser or match a help substring.

Use these existing examples:

- [Pilot inquiry tests](../../tests/integration/test_leaf_pilots_cli.py) for scripted native requests/responses.
- [Runtime CLI tests](../../tests/integration/test_leaf_runtime_cli.py) for live/refresh/offline equality, empty/error preservation and strictness.
- [CLI grammar tests](../../tests/integration/test_leaf_cli_contract.py) for dotted identity and action-first syntax.
- [Lifecycle tests](../../tests/integration/test_plugin_lifecycle.py) for install, uninstall, retained storage and concurrency.
- [Adapter interface tests](../../tests/test_plugin_interface.py) for callable compatibility without executing business methods.
- [Package tests](../../tests/test_leaf_package.py), [helper tests](../../tests/test_plugin_helper.py) and [distribution tests](../../tests/test_leaf_distribution.py) for delivery boundaries.
- [Progressive help tests](../../tests/test_current_help.py) for declaration-driven navigation without adapter activation.

For each migrated leaf, cover verified request allowlisting, scope/pagination and
native parsing, authentication/business failures, declared identity/unknown
semantics, supported filters and native detail where applicable. Prove default
list is offline, live never publishes, accepted nonempty refresh replaces the full
slot, and empty/error/strict rejection preserves prior rows and capture time.
Display projection/windowing must not truncate acquisition. Changed adapter or
technical contracts may reject old snapshots with `CACHE_CONTRACT_CHANGED`;
refresh rather than rewriting old cache to appear compatible.

Run focused tests while developing, then required repository gates:

```bash
uv run python -m pytest -q
uv run ruff check .
uv run ruff format --check .
make doc-guard
git diff --check
```

Apply the current repository review workflow. Report local tests/review, remote CI,
production UAT and release independently; automated passing tests do not qualify a
production inquiry.

## 7. Apply the evidence to a real rewrite

[Spec #255](https://github.com/proletariat64/dogopencli/issues/255) defines the
four-pilot independence and business acceptance gate. The evidence companion
records which checks have actually passed. Required production evidence must be
present before this pattern is described as proven. The broader migration map
remains paused until separately resumed; this handbook does not resume it.

The four pilots have now passed independent installed execution, isolated
same-input release comparisons and per-leaf nonempty production UAT, as recorded
in the [evidence companion](leaf-handbook-evidence.md). The resulting migration
method is leaf-owned native business behavior under current contracts, direct
imports of genuine host primitives, isolated release-tag comparison, retired-file
and transitive-consumer checks, installed-artifact proof and per-leaf business UAT.
These examples do not establish arbitrary module-loading or complex-leaf support.

1. Identify a supported inquiry and its historical contract, tests and UAT. Use
   current dotted-name practice. Assess simplicity by actual behavior: verified
   endpoint/envelope/identity, ordinary paging, no backend workaround, custom
   assembly or auxiliary-loader requirement. Short adapter code alone is not
   evidence of simplicity. Record the reason for its place in the proposed order.
2. Write against the current leaf interface using that knowledge. Reproduce the
   native request/response contract with shared host mechanics, and verify business
   output parity: fields, types, identity, scope, detail and quality semantics.
   Retrieve historical Python only from a pinned GitHub release tag into an
   isolated location outside the repository and new runtime. Never import, wrap,
   call, re-export or copy the retired business runtime into the new distribution.
   Replay identical inputs in separate historical/new environments and compare
   fields, types, amounts, identity, counts and multiplicities. Verified native
   business meaning takes precedence over historical defects; explain differences
   and return unresolved business ambiguity to the owner.
3. Use task-isolated configuration and freshly collected replacement state where
   appropriate. Before any reset, inventory the exact configuration, query cache,
   Duckdog database/tables and authentication profile it affects. Reset is optional
   and requires task authorization. Ordinary uninstall retains Duckdog data;
   refresh does not import business rows into Duckdog. Preserve the current daily
   installation when validating #255; no global installation or deployment is
   part of acceptance.
4. Pass the public CLI tests and perform inquiry-only production UAT for the new
   leaf and native get if declared. Compare full records under matching bounded
   scope and investigate changing data instead of enforcing historical counts.
   Record revision/package, capture time, scope, counts and quality limitations.
   Prove live, refresh and offline behavior separately. Blocked UAT is incomplete.
5. Follow repository browser instructions before UAT: task-owned config/profile,
   unused allowed CDP port, human SSO where required, never ports 9330–9340 or
   borrowed sessions. Keep raw data/authentication private; publish sanitized
   evidence. No business mutations or automatic dataset ingestion.
6. Inventory every retired implementation and retained host primitive. Check
   direct and transitive consumers and remove obsolete code, registration, tests,
   scripts and active guidance. Inspect wheel and sdist contents; install outside
   the checkout, install the packages through public lifecycle commands and run
   positive inquiries in fresh processes with controlled transport. Reject retired
   imports and verify module origins. Static checks and positive execution jointly
   establish independence; neither replaces production business UAT.
7. Record actual auxiliary-file/multi-module requirements for complex leaves,
   validate each needed loading pattern, and update this handbook from the results.
   Complete per-leaf checks/review and evidence before progressing. Track the
   remaining inventory only after the paused migration map is explicitly resumed.

Normal installation does not run production UAT. The synthetic exercise validates
the standard development path; each real inquiry still needs its own installed
artifact, same-input comparison and production evidence. Unknown FX business
identity and total semantics remain explicit limitations, not completeness proof.

# Collection configuration PR review validation

Observed: 2026-09-27
Scope: general
Status: snapshot

Review target: [PR #49](https://github.com/proletariat64/dogopencli/pull/49),
initial head `179631238bed8d800849a98389499d845cb219fa`.
Inputs: the operator-provided Qoder Standards/Spec report and GitHub's
Greptile check/comment for that exact head.

## External review status

Greptile Review completed successfully, confidence 5/5, with no actionable
findings and no inline review comments. This is the only check returned by
GitHub for the inspected head; the supplied Qoder report is not represented
as a separate GitHub check. A successful review does not substitute for tests.

## Qoder findings, individually validated

| Finding | Disposition | Evidence and reasoning |
| --- | --- | --- |
| 1. Mysterious Name | No change | `network_config` groups the two concrete configuration capabilities beneath the verified `networkConstruction` menu. Its module declares both concrete names; CONTEXT defines the business objects separately. An implementation grouping need not become a new domain entity or synonym. |
| 2. Duplicated Code | Refresh duplication fixed | The capacity and configuration refresh bodies were identical apart from capability and failure text. `_refresh_complete_collection_list` now owns locking, acquisition, completeness gating, sorting, snapshot metadata, deadline checking, publication and output. Three refresh commands delegate to it. Original error strings and ordering remain unchanged. |
| 2. List orchestration similarity | Retained | The small list entry points select different filter declarations and cached-row validators (`ruleId` versus `id`). They already reuse transport, collection, cache reads, display validation and output. Sharing the entire entry point would require additional callbacks or a broader capability interface; no divergent behavior was identified. |
| 3. Repeated Switches / Feature Envy | No change | Both conditionals occur in the single offline description provider. They select evidence-aware field descriptions and the card-only array annotation. Moving this text onto the runtime capability would mix description evidence into the acquisition object without removing a demonstrated maintenance defect. |
| 4. Data Clumps | No change | Each immutable, typed pair is exactly a CLI flag and its raw field name. Consumers unpack both explicitly; no third attribute or behavior needs an independent `FilterSpec` type. |
| 5. Middle Man | No change | Handler strings resolve through `globals()[node.handler]`. Named wrappers bind capabilities to that existing dispatch contract and keep public command bindings explicit. |
| 6. Catalog facade bypass | No change | The plugin registry supplies query declarations; the static catalog already assembles groups and refresh commands separately. Importing the two capabilities and their refresh-node factory does not bypass a documented universal registration contract. Offline catalog/navigation tests cover this assembly. |

The Spec verdict remains supported: the refactor does not change endpoints,
filters, source namespaces, parser rules, cache/live behavior, schemas or help.
In particular, `rebuild_page_size=None` disables rebuild fallback; single-page
enforcement also relies on parser coverage checks and fixed request values.
That property does not follow from `rebuild_page_size` alone.

## Verification boundary

The implementation baseline passed 944 tests and 23 subtests, plus the recorded
[full argument UAT](2026-09-27-collection-network-config-uat.md).
Those results describe `1796312`, not a fresh full-suite run after this refactor.

For the extraction, AST comparison of each original refresh body against the
new helper passed after substituting the capability and exact failure message.
The complete VA-capacity and network-configuration CLI SIT files, plus catalog
and help tests, form the focused regression set. Production UAT was not repeated
because no request contract or externally visible behavior changed.

Ruff lint/format and whitespace checks passed. CLI typechecking retains 25
baseline diagnostics; the existing frozen VA capability versus writable
`Capability` protocol mismatch moves into the shared helper without adding a
new diagnostic category. The focused regression set passed: **290 tests in
177.89 seconds**. Doc guard passed across 50 Markdown files.

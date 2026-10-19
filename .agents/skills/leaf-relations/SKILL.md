---
name: leaf-relations
description: Help leaf development classify scoped inquiries as simple or complex, discover frontend and PDKB relationship candidates, run bounded experiments, and obtain human confirmation before producing a spec and sample.
---

# Leaf relationships

Help the main agent understand a leaf's business structure. Return a confirmed
spec and minimal sample to [leaf-dev](../../../tools/leaf-dev/README.md), which
owns implementation and acceptance. This helper does not implement the leaf.

Start a private working record from [record.yaml](references/record.yaml). It is
a note template, not a workflow interpreter or proof of approval. Fill only what
happened; keep actual user replies as confirmation references. Use private
evidence paths rather than requiring old UAT files or caches to exist.

## 1. Light scan

Establish the assigned leaf, operations and requested output. Query PDKB using
`graphify query` or `graphify explain`, then verify cited source documents. Read
the current frontend's labels, request bindings, navigation arguments and data
flow. Compare native response structure with fields added by the UI.

Use prior UAT if available; fresh, small inquiry-only product calls are allowed
for the scan. Follow the repository's endpoint verification, authentication and
browser ownership rules. A scan checks representative structure, not all pages
or automatic per-row detail calls. If access fails, report the evidence gap.

Propose exactly one scope-relative classification and confidence (1–5/5):

- **simple:** the requested inquiry preserves its native records, including
  nested JSON, without resolving a new business relationship. Out-of-scope
  details/history can remain candidates without changing the classification.
- **complex:** the requested output needs business relationship decisions or
  acquisition beyond a qualified standard binding. If the relationship needed
  by the scope is not established, propose complex with the evidence gap,
  rather than a third classification.

Nested shape or endpoint count alone does not decide the class. Distinguish row
identity from parent references, same-object detail from children/history, and
native nested fields from frontend enrichment. State counterevidence and limits;
one matching sample or label does not prove a join or universal uniqueness.
An already qualified same-object List-to-Get binding can use standard composition
without a new relationship decision. A newly proposed binding needs evidence and
HIL covering lookup identity, required context and native-root coverage.

## 2. HIL①: scope and plan

Present one short packet covering **all relevant candidates**, using this format:

```text
Leaf / scope:
Judgment: simple | complex; confidence x/5
Evidence: key facts and source references
Candidates: relation; effect on this scope; recommended treatment
Proposed output: short JSON shape or example
Gaps / decisions: bundled questions for this stage
Confirm: accept or adjust classification, scope and proposed experiments?
```

Wait for the user's explicit acceptance or adjustment, even at 5/5. Do not infer
acceptance from the original development request, confidence or a filled YAML
field. Discuss follow-up questions together; HIL can take several rounds.
Newly discovered relationships do not expand scope without acceptance.

For accepted simple scope, proceed to spec/sample. For complex scope, perform
the accepted bounded experiments, then present HIL②.

## 3. Experiment and HIL②

For each in-scope candidate, compare frontend mapping with native requests and
responses: parent/child identities, grain, direction/cardinality, parameters,
dates/scope, source-specific pagination and completeness. Seek counterexamples
such as repeated parents with valid distinct children. Separate confirmed empty
from unqueried, failed and unknown; never turn incomplete retrieval into absence.
Keep observations limited to their tested scope.

Reuse the packet above for HIL②: present the proposed model/output, all experiment
results and unresolved decisions together. Ask the user to confirm or revise the
model and its limits. Record the actual reply and which scope/relations it covers.
An experiment, passing UAT or an agent-authored `verified` field cannot supply
human confirmation. Material contradictory evidence returns to the relevant HIL.

## 4. Spec, sample and explicit handoff

After acceptance, produce a concise spec recording grain, native identities,
relations, acquisition scope, output shape, per-source completeness, failure/empty/
unknown semantics, acceptance criteria and implementation gaps. Clearly separate
accepted facts from unresolved candidates. Link evidence and HIL confirmations.

Use the existing [SDK sample](../../../tools/leaf-dev/example/) and
[interfaces](../../../tools/leaf-dev/interfaces.md) for minimal sample code, with
synthetic data. [Examples](references/examples.md) illustrate preservation and
scope decisions. Keep coding guidance in the existing handbook/interfaces;
[plugin-helper](../plugin-helper/SKILL.md) remains the verify/pack helper.

Read [Get SDK](../../../docs/agents/get-sdk.md) when scope includes direct detail
or List plus Detail. Standard composition requires an explicit qualified
`list_binding`; `list --live --with-detail` queries only selected rows and returns
`{record, detail}` pairs. Qualify lookup versus returned identity, same-value List
source, every required context field and failure/coverage semantics. A native root
may contain nested children; separately paged history or child endpoints remain
outside this composition. Direct Get is independent and may be Get-only.

List and Detail parsers receive response bytes, not a query session. For joins,
transformed bindings, extra child/history acquisition or other unsupported
composition, report the precise execution gap and a non-executing output sketch.
Keep SDK extensions and existing HOLD scope as separate assigned work; never
invent a collector or parser-side queries to make a sample appear supported.

Finally ask: **“转入／继续开发，还是研究到此结束？”** Bundle this with the final
HIL packet when practical. Wait for the explicit choice; the original task does
not substitute for it. Continue hands the spec/sample to the main agent's
leaf-dev flow; end preserves results and stops. Continue does not authorize SDK
changes. Report unresolved implementation gaps in either handoff.

Private HIL shows the data owner's original business values unless they request
masking. Git, public tickets and OCR receive only synthetic/redacted content or
private evidence references. Credentials stay excluded from all such artifacts.

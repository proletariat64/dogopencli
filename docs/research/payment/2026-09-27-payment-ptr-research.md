# Payment PTR inquiry research and Graphify/wiki cross-check

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Findings and evidence boundary

PTR means **production trial run (仿真生产验证)**. The original definition spells
it `prodution-trial-run`; this report corrects that spelling, not the meaning
(D1:2–6). It is a production verification product for bank services and funding
paths. Reading existing PTR records belongs in the inquiry CLI; starting a PTR
can create real payment activity and remains excluded.

The historical production survey identifies seven payment PTR menus. They are
seven candidate inquiry resources, not seven verified API contracts. This
research covers their domain distinctions, candidate queries, source conflicts,
command boundaries, and the production verification needed before implementation.
**No PTR capability is implementation-ready on this evidence alone.**

Evidence has four different levels:

| Evidence | What it establishes | Limitation |
| --- | --- | --- |
| Original PTR PRDs, training and product summary, D1–D9 | Domain intent, model evolution, historical acceptance issues | Designs and historical descriptions do not prove current API behavior |
| Existing Graphify graph | Source discovery and relationships | Truncated results and incorrect acronym expansions were observed |
| Existing LLM wiki, W1/W2 | A secondary synthesis to cross-check | Derived from the same product corpus; not independent corroboration or a production contract |
| [2026-09-08 production survey](2026-09-08-payment-operations.md) | Seven native menu paths and visible PTR lists | Explicitly leaves PTR API mappings and state semantics unverified |

Current public `payment` help exposes `rules`, `channel`, `cost`, and `sla`, with
no PTR group. GitHub issue [#59](https://github.com/proletariat64/dogopencli/issues/59)
reserves PTR for a subsequent `payment ptr` scope. No issues, executable commands,
production configuration, Graphify graph, or wiki content were changed by this
research.

Current production verification is **blocked by browser availability**: the
supported browser runtime returned `No browser is available`, and its browser
inventory was empty. The user was asked to connect the signed-in browser.
No current PTR requests, permissions, counts, schemas, or detail identities were
verified. This is not evidence of expired authentication or denied PTR access.

## Method

Queried the existing graph at
`~/dev/dogpdkb/graphify_flatten_ready/graphify-out/graph.json`, then inspected the
cited original Markdown and existing wiki. Queries included PTR terminology,
test cases, patrols, beneficiary accounts, and automation batches. Broad queries
were truncated and sometimes matched unrelated domains; targeted source reads
were used to resolve those gaps. No graph rebuild, extraction, wiki generation,
or saved Graphify query output was performed.

The repository's historical survey, domain vocabulary, cache ADRs and public
CLI help supplied integration constraints. The code graph was consulted but its
build SHA differed from current HEAD; no broad structural conclusion was drawn
from it and no code edits were undertaken. This report is an authorized research
summary, not a frozen specification or implementation acceptance report.

## Domain model and interpretation

| Object | Meaning and distinctions to preserve | Evidence |
| --- | --- | --- |
| Outflow network baseline/view | Account/network capability and verification/performance summary; not an individual PTR run | D1:105; D3:67–78; D5:7–14 |
| Test case | Reusable test inputs, scenario/type and expected behavior; not the resulting order | D3:88–95; D6:5–22 |
| PTR order | One initiated verification's business record with payment and verification fields | D3:160–169; D7:939–1004 |
| Automation batch | Historical native menu for automatic flow management; exact batch grain and relations remain unverified | Historical production survey, PTR menu map |
| Beneficiary account entry | PTR receiving-account library entry and binding/test-purpose metadata; not interchangeable with a bank-account identity or VA rule | D3:219–230; D5:422–464 |
| Patrol rule | Schedule/configuration that can generate new PTR orders from a case | D9:148–177 |
| Patrol batch | A periodic inspection batch, distinct from its related baselines, rules, execution tasks and orders | D5:7–14, 42–51 |

D5 names separate baseline, case, inspection-batch, batch-to-baseline,
batch-to-rule, execution-task, order and verification-notification-task models.
Those table names help establish object boundaries; they are **not API paths**
and do not authorize database access. No evidence establishes that automation
batches and patrol batches share an identity or endpoint.

Do not collapse the following concepts:

- **Configured capability, requested test, observed result:** D7:966–987 separately
  describes OBO/FVT/non-UD requirements, network support and verification results.
- **Payment status, verification progress, final verdict:** D7:945–946 and 995
  describe `order_status`, `verify_status`, and `final_verify_result`. These are
  source database field names, not verified response keys.
- **Verified versus passed:** training says INIT means no verification result;
  VERIFIED means a result exists (D4:139,148). It does not mean PASS.
- **Expected rejection versus failure:** an `effective` case may deliberately
  require transfer rejection; that rejection satisfies the expected behavior and
  yields a PTR pass (D6:11–14,19–20). A `negative` case is likewise not shorthand
  for an unsuccessful test. Preserve the source case type and final verdict.
- **Typed identifiers:** D7 separates PTR order ID, allocation order ID,
  financial-network ID, outflow baseline ID and beneficiary card index. Do not
  offer one untyped ID or automatically traverse unrelated order systems.
- **Summary versus evidence:** a network aggregate is not a single order result
  or a universal guarantee of current channel health. D3 includes both PTR and
  non-PTR observations in some aggregates; later designs introduce batch and
  rolling-period calculations (D5:297–334). Do not recompute these locally.

The 2025 summary describes narrower bank-service verification, explicitly
excluding payment/collection single-end validation (D2:1–5). D1 includes broader
end-to-end ambitions and unanswered design questions. For this CLI, use existing
payment PTR records as the boundary; do not turn aspirational platform coverage
into supported capabilities.

## Seven-menu inquiry and command map

Paths below are relative to
`https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/productPTRManagement/`.
They were observed on 2026-09-08 and need current revalidation. Command names
are proposals, not registered commands or a published specification.

| Native menu/path | Proposed list command after verification | Candidate selectors and output | Resource-specific gap |
| --- | --- | --- | --- |
| Outflow Network View — `outflowNetworkView` | `payment ptr networks list` | Entity, channel, debit-account alias, debit/credit currency, credit region, clearing network, configured OBO/FVT, result-update time; later design adds verification/patrol result, in-scope and available-beneficiary distinctions (D3:67–78; D5:23–57,121–241) | Stable baseline identity, summary provenance, result/scope semantics, actual aggregate time window |
| Case Library — `caseLibrary` | `payment ptr cases list` | Channel, debit account, currencies, network, OBO/FVT/non-UD; case type; preserve inputs and expected results (D3:88–90; D5:248; D6) | Case/group/version grain, actual types, true detail endpoint, account references |
| Order Inquiry — `orderInquiry` | `payment ptr orders list` | PTR order ID, case ID, update time, entity, channel, account, currencies, network, order state; verification state/verdict are distinct candidates (D3:160–162; D7) | Default/ranged history coverage, time zone, typed IDs, independent detail permissions, exact filter keys |
| Auto Flow Management — `autoFlowManagement` | `payment ptr automation-batches list` | Batch identifier, state, time and related-record selectors are discovery questions, not established filters | Native API, batch grain, parent/child links, counts/status, child pagination; weakest primary-source mapping |
| Beneficiary Account Library — `beneficiaryAccountLibrary` | `payment ptr beneficiary-accounts list` | Channel, account alias/number, currency, entity, region, account type and state (D3:219–230); test-purpose distinction is a later design (D5:422–459) | Entry/card-index identity, masking, field permissions, normal/bad account distinction, non-VA/VA boundary |
| Patrol Rule Library — `patrolRuleLibrary` | `payment ptr patrol-rules list` | Rule ID, associated case/network, schedule and enablement/approval are discovery candidates (D9:148–177) | Current rule schema/version, time zone, schedule semantics, filter keys and status vocabulary |
| Patrol Batch Library — `patrolBatchLibrary` | `payment ptr patrol-batches list` | Batch ID, related rule/network, time and batch state are discovery candidates (D5:7–14,42–51) | Current batch schema, history scope, child coverage, relationship filters and status vocabulary |

Add `get` only where a separate, inquiry-only detail contract is proven. An early
case-library action named “PTR detail” leads to order management (D3:91–93);
that label does not prove a case-detail API. Likewise, “verify again” or a modal
showing editable results is not a read-only detail operation.

Keep all seven resources in the research scope. A provisional delivery sequence
is networks and cases first, then orders and beneficiary accounts, then patrol
rules/batches and automation batches. This reflects evidence strength and the
need to define bounded history, not a technical dependency or an instruction to
implement before each contract gate passes.

## Graphify and LLM wiki cross-check

| Claim or omission | Source check | Finding for CLI research |
| --- | --- | --- |
| Graphify expands PTR as Payment Transfer Routing / Payment Transfer Request | D1:2 explicitly defines production trial run | Incorrect extraction; reject these expansions |
| W1 calls PTR product test/verification | Broad intent agrees with D2, but is not the original acronym | Use production trial run and retain the Chinese definition |
| W1 says discovered defects were pre-production | D2:22–28 labels them production issues; D1:2–6 explicitly describes production validation | Wiki wording is misleading; PTR can involve real production activity |
| W1 summarizes OBO/FVT/GPI/VA coverage together | D2:49–54 distinguishes outflow and inflow; outflow GPI is unchecked/manual, inflow GPI checked/manual in that matrix | Do not infer uniform automated coverage or current availability |
| W1 quotes outflow 91.6% (667/728), inflow 51.3% (184/359), and 47 unused paths tested | D2:17 supports the historical figures | Accurate source snapshot, not current production counts or pagination totals |
| W1 summarizes bank-service verification and not single-end flows | D2:1–5 supports this; D1 contains broader earlier ambitions | Keep product summary and roadmap intent separate |
| W1 has no endpoint, pagination, seven-resource identity or filter contract | Original PRDs provide domain detail but still no current native contract | Neither wiki nor graph can unblock implementation alone |
| Wiki labels its confidence source-backed | W2 identifies a 4,588-document snapshot synchronized 2026-08-11; W1 metadata is 2026-08-16 | Same-corpus secondary evidence, with different snapshot timing from this research |

W1/W2 were inspected as existing artifacts. Corrections are recorded here;
the wiki and knowledge graph remain unchanged.

## Conflicting and evolving historical requirements

1. **Patrol status:** D5:42–51 proposes completed/not-inspected/failed, but its
   acceptance notes at line 508 describe `inspectionStatus` with INIT/FINISHED,
   associated with inspecting/completed, and mark follow-up work. Neither is a
   safe current closed enum. Preserve observed backend values once verified.
2. **Network verification precedence:** D5:35–38 gives examples for all-pass,
   any-fail, any-INIT and never-tested networks without defining precedence for
   mixed fail/INIT observations. Do not invent a reduction algorithm.
3. **Result provenance:** D8:1 proposes manual marking > manual receipt > GPI >
   statements, but line 4 explicitly leaves a manual-mark/manual-receipt conflict
   unresolved. Lines 6–11 distinguish evidence usable for OBO versus FVT/time.
   Reading results should preserve provenance; it must not reproduce an
   unverified adjudication engine.
4. **Scope eligibility:** D5:121–241 evolves account/network inclusion through
   account eligibility, network availability, beneficiary matching and online
   gray/enabled states. D2:32–38 adds the requirement for an available receiving
   card. Scope membership, card availability, network state and successful PTR
   are different dimensions; do not reimplement historical SQL as current scope.
5. **Beneficiary identity:** D5:424 proposes account number plus test purpose as
   idempotency identity, with normal/bad accounts. This is evidence against
   account-number-only deduplication, not proof of a public composite ID.
6. **VA separation:** D5:442 proposes moving VA numbers into a separate PTR VA
   library and explicitly excludes that work from June scope. No current menu
   or migration outcome is established; do not treat beneficiary accounts as a
   collection VA pool or infer that all entries are non-VA.
7. **Context propagation:** D5:554 records a patrol-batch navigation bug that
   lost the selected network. Clicking through from a network is not proof that
   the returned batch list is filtered to that network.
8. **Performance:** D3:75 and D5:297–334 describe different aggregations and
   periods. The latter's statistical labels/formulas are design evidence, not
   validated estimators. Expose verified backend fields with units/provenance;
   do not calculate SLA compliance or new confidence intervals from them.

## Production contract research still required

For each of the seven native pages, record the following without retaining
production entity values or authentication data in the report:

1. Confirm current menu, frame/origin, payment/outflow scope and query permission.
   Observe actual native Search/list requests and safe Detail requests; freeze
   method, host, path, encoding and permitted action/parameter names. HTTP method
   or a query-like name alone is insufficient to authorize a request.
2. Capture sanitized nonempty field/type schemas, success/error envelopes, null
   behavior and pagination metadata. Record UI defaults, hidden direction and
   date constraints. Shared inflow/outflow designs make direction isolation an
   explicit gate.
3. Establish stable row identity and versions. Compare each sampled detail ID,
   object kind and version with the requesting row. Case ID, baseline ID, order
   ID and both batch types must not be interchanged.
4. Verify page base, supported sizes, sort, exact/full-page boundaries, empty and
   beyond-end behavior, duplicates, repeat reads and changes during acquisition.
   Do not inherit another endpoint's 1,000-row strategy or equate deduplication
   with complete coverage.
5. Map every candidate filter to observed request/response fields; explicitly
   include or defer it. Verify single/multiple values, time inclusivity, time
   zone, exact versus substring matching, nulls and literal wildcard behavior.
   Related predicates must refer to the same related object.
6. Validate genuine detail and child-list boundaries independently. Counted
   children, summary fields and the first child page do not prove full detail.
   Record permission refusal separately from an empty record or missing ID.
7. Establish the complete acquisition scope for mutable orders and batches:
   time range, cutoff/watermark, update handling and retention. A hidden recent
   period must never be advertised as all history. Decide acceptable freshness
   explicitly before applying the shared 72-hour cache default.
8. Inventory account/name/address and banking-message fields before deciding
   output and cache retention. Keep raw responses and business identifiers out
   of Git/logs; use synthetic fixtures and approved private local storage for
   any later necessary evidence artifacts.

Do not inherit the ordinary payment-order access denial: the historical denied
endpoint belongs to `operationalDisposal/orderOperation`, whereas PTR uses
`productPTRManagement/orderInquiry`. PTR permission is currently **unknown**.
The recent [flow-rule blocker](2026-09-27-payment-flow-rule-blocker.md) also shows
why HTTP/business success must be followed by identity validation.

## Inquiry boundary and integration recommendations

Allow only verified reads of existing records. Exclude case creation/editing,
single/bulk PTR launch, approval submission/approval, withdrawal, retry,
result verification/correction, receipt upload, account binding/import,
enable/disable, patrol scheduling/triggering, and server-side export jobs.
D3:91–95,163–169,221–233 and D9:170 demonstrate that query pages contain these
state-changing actions. A “test” label does not make them harmless reads.

For accepted capabilities, reuse the existing restricted transport,
authentication, output and snapshot infrastructure. Each resource needs its own
source/namespace and offline help/describe contract. Keep configuration, order
history and batch-history scope separate. [ADR 0003](../../adr/0003-local-query-snapshots.md)
requires default offline reads, explicit live reads without publication/fallback,
and atomic complete refreshes preserving the old snapshot on failure. PTR history
may require an explicit bounded-scope decision before that policy can apply;
this report does not silently change the ADR.

Implementation acceptance should combine public CLI tests, synthetic rejection,
auth, pagination, identity and partial-detail failures, plus native production
inquiry evidence and private-cache verification. Document every supported
parameter's evidence and deferred behavior. Publish specs in GitHub Issues only
after the research outcome and remaining gates are reflected accurately; no
placeholder command should imply a working PTR capability.

## Source register

D1–D9 are files relative to
`~/dev/dogpdkb/graphify_flatten_ready/`. Line numbers refer to those flattened
Markdown files, including HTML/OCR and table lines. Filenames are export labels;
internal document content, rather than filename dates or filesystem mtimes,
determines whether a statement is a plan, historical result or observation.

| Ref | Source file | Principal passages |
| --- | --- | --- |
| D1 | `收付款产品__PTR__总结分析规划__PTR质量产品的方案说明-2026-04-19-[184564144].md` | 2–6 definition; 10 broader ambition; 35–44 views; 105–147 capabilities and patrols |
| D2 | `收付款产品__PTR__总结分析规划__PTR产品总结-2025-04-08-[269471849].md` | 1–19 positioning/coverage; 22–28 production defects; 32–54 scope/acceptance; 63–72 lifecycle and inflow limitations |
| D3 | `收付款产品__PTR__需求方案PRD__线上环境验证能力建设-流出PTR第一期指定网络-同币种流出PTR__流出PTR第一期前端需求详解-2026-04-19-[192665558].md` | 67–95 networks/cases; 160–169 orders; 219–233 accounts |
| D4 | `收付款产品__PTR__需求方案PRD__线上环境验证能力建设-流出PTR第一期指定网络-同币种流出PTR__流出PTR第一期-产品使用培训-2026-04-19-[220447861].md` | 139,148 verification progress; 161–172 manual correction |
| D5 | `收付款产品__PTR__需求方案PRD__6月ptr需求汇总-2023-07-13-[256986267].md` | 7–14 model grains; 23–57 status aggregation; 121–248 scope/case type; 297–334 performance; 422–464 accounts; 508,554 acceptance conflicts |
| D6 | `收付款产品__PTR__需求方案PRD__PTR用例模型与业务判定规则-2026-04-28-[197374244].md` | 5–22 expected outcomes, positive/negative/effective cases |
| D7 | `收付款产品__PTR__需求方案PRD__PTR产品治理需求list-2023-05-23-[245745649].md` | 939–1004 order model, typed links, test inputs/results and provenance |
| D8 | `收付款产品__PTR__需求方案PRD__线上环境验证能力建设-流出PTR第二期__PTR验证结果判定规则-系统判定-人工判定-2023-02-22-[224957749].md` | 1–11 evidence priority, unresolved conflict and result dimensions |
| D9 | `收付款产品__PTR__总结分析规划__CY23流出渠道范围与PTR业务验证节奏__2月流出PTR验证提效-2023-03-09-[225880351].md` | 148–177 rule schedules, new orders and approval |
| W1 | `/home/ubuntu/.openwiki/wiki/topics/payments-collections.md` | 22–24 PTR synthesis; page metadata 2026-08-16 |
| W2 | `/home/ubuntu/.openwiki/wiki/sources/git-repo.md` | 10–16 corpus origin/snapshot; source list identifies D2; final search guidance says summaries are selective |

## Completion record

- Source and existing Graphify/LLM-wiki cross-check: completed for the domain and
  seven-menu research map; unresolved automation-batch semantics recorded.
- Current native production contracts: not verified; browser connection missing.
- Implementation/spec readiness: pending resource-specific contract gates above.
- Deliverables: this research snapshot and its entry in the documentation index.

## Subsequent specification publication

Following the user's request to turn the design into specs and tickets, the
[PTR parent specification #61](https://github.com/proletariat64/dogopencli/issues/61)
was published with seven resource-specific child specifications. It includes
the research snapshot for remote review. The observation-time statements above
remain historical; publication does not establish current production contracts.
The tickets start at `needs-info` for the recorded evidence gaps and can advance
independently after their native inquiry contracts are verified.

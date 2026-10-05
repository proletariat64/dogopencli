# Batch F F2 rule-status contract: evidence and deferral

Observed: 2026-10-06
Scope: general
Status: snapshot

Research for [#117](https://github.com/proletariat64/dogopencli/issues/117)
(Batch F F2, `liquidity operations rule-status list`), tracked under parent
[#72](https://github.com/proletariat64/dogopencli/issues/72). The round's PRD
review and CDP investigation were completed in the issue; this document records
the verified evidence chain and the decision to keep the leaf deferred. No list
is enabled, no production CLI UAT was attempted, and no live CDP probing was
performed for this document.

## PRD object model

The Liquidity product whitepaper (P1, *国际流动性产品白皮书*, source
197368565, lines 385–409, verified against the knowledge-base original on
2026-10-06) describes rule-based operation as a chain of distinct objects:
configured transfer rules, automatic rule triggering, generated tasks, transfer
orders sent to the transfer center, and execution receipts that update the
acceptance record to success or failure. Rule configuration state (RUN/PAUSE)
is therefore not one execution and not an actual transaction result; a rule
runtime status inquiry must observe executions or their receipts, not
configuration rows.

## Native investigation outcome

The issue's 2026-10-06 investigation established that the current frontend
assets are byte-identical to the previously inspected historical bundle.
Inspection of the native rule configuration and task pages, plus static call
inspection of those assets, found no independent rule-status runtime-list
caller, payload or record identity. The existing rule configuration list and
decision task list are different PRD objects; renaming either as rule status
would misrepresent configuration state as execution outcome.

## Decision

The leaf stays deferred with its named blocker (`runtimes`, status
`unverified`). The registered reason now carries the specific blocker: no
independent native runtime-list caller, payload or identity; configuration
RUN/PAUSE is not one execution or an actual transaction result; existing rule
configuration and decision task lists are not renamed as rule status. No
request was invented and no schema was guessed.

Discoverability and refusal are externally tested through the public
disconnected CLI (help/describe/snapshot expose the deferred status and named
blocker; cached `list` exits 1 with `UNSUPPORTED_CAPABILITY`; `--live`,
`--require-complete` and `refresh` exit 2 with `INVALID_ARGUMENT`; no cache
mutation) in `tests/integration/test_liquidity_rule_status_gate.py`. The
unsupported-leaf count in the snapshot CLI SIT is unchanged.

## Remaining evidence work

Per the issue's next actions: if a real source provides rule run observations,
freeze the object as the source's actual rule run observation with per-rule,
per-task or per-observation granularity, typed identity, status source, native
observation time and scope, then obtain the exact query contract from real page
calls. If no independent native object exists, record a business naming/scope
decision request and keep the leaf unsupported. Investigation ending this round
is not delivery; production UAT was not attempted.

Prior evidence: the 2026-10-01 live-probe audit recorded this leaf as
`runtimes/unverified` with no verified independent native contract; the Batch F
investigation refines, not replaces, that blocker.

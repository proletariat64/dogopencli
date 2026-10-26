# Shared result policy

The host owns acceptance, diagnostics, process status and atomic cache publication
for standard and custom List, Get and Refresh. Leaves own verified native parsing,
identity, scope, business relationships, applicability and qualification of retained
gaps. Domain modules declare identity/authentication, not per-leaf result procedures.

## Acceptance

Every List, Get and Refresh exposes `--require-complete`. It changes acceptance
only: scope, freshness, endpoints, retry limits and request budgets stay unchanged.
Projection, local filtering, offset and display limit cannot improve acquisition
coverage or shrink a Refresh candidate.

| Candidate | Default List/Get | Strict List/Get/Refresh | Default Refresh |
| --- | --- | --- | --- |
| Complete valid result, including recovery warnings | Data, exit 0 | Data, exit 0 | Publish if nonempty, exit 0 |
| Explicitly qualified usable incomplete or unproven coverage | Data and warnings, exit 0 | `INCOMPLETE_RESULT`, no candidate data, exit 1 | Publish if nonempty with gaps and warnings, exit 0 |
| Missing required information, unqualified gap or hard failure | Specific failure | Same specific failure | Preserve previous capture |
| Qualified complete empty result | Native empty shape, exit 0 | Same | No replacement, exit 0 |

An empty incomplete result never replaces a capture; strict mode still rejects it.
A valid empty response differs from an unresolved prerequisite or verified not-found.
Warnings alone do not mean incomplete. Native count equality, deduplication or zero
rows alone do not prove coverage.

`AcquisitionEvidence` records requested scope coverage, dataset coverage, observed
counts, native total semantics, attempts and reasons. Its `usable_incomplete`
boolean is persisted and defaults to false in direct construction. The collection
SDK supplies its qualified traversal policy. Custom operations must explicitly
qualify useful partial candidates and retain component attempts and applicability.
A required component failure remains fatal. A supplementary component may be
optional for usability while remaining part of the completeness promise. Verified
inapplicability creates no gap; unknown or unattempted coverage is not absence.

Only explicitly qualified retained refusal/failure categories may be gaps.
Custom Get additionally declares supplementary queries and permitted retained
categories; existing custom List policies retain their independent qualification. Authentication/permission loss, transport, timeout, budget exhaustion,
malformed response, scope violation, identity conflict, corrupt configured sources
and unknown business errors remain failures, even when an adapter catches them.
The host has no native-code allowlist, failure percentage threshold or stale-data
filling policy. Native paging and recovery qualification remain authoritative.

`check_complete(evidence, require_complete=..., mode=...)` returns one shared
`ResultDecision` or raises a structured failure. Rendering and storage consume
that decision. Leaves do not print diagnostics, choose process exits or publish.

## Envelope and diagnostics

The common envelope remains `data`, `meta`, `error`. Accepted results have no fatal
error. Rejected results contain no candidate data and retain safe coverage evidence
and diagnostics. `meta` keeps three facts separate:

| Field | Values and meaning |
| --- | --- |
| `outcome` | `success`, `warning`, `failed`: operation result. |
| `data_quality` | `complete` or `incomplete` for candidate coverage; `unusable` for a hard failure without accepted data. |
| `publication.status` | `not_requested` for Get/live List; `published` or `unchanged` for Refresh. |
| `publication.reason` | Null when not requested; `accepted`, `empty_result`, `rejected` or `not_published` as applicable. |

`complete`, `dataset_complete`, `acquisition`, counts, original `fetched_at`, warnings
and actual `published` remain available where relevant. A Get's coverage describes
its declared native response/components, not an unconditional business-wide dataset.

`dogopencli.errors.diagnostic(...)` supplies one schema for errors and warnings:
`code`, `message`, `severity`, `origin`, `stage`, `component`, `scope`, `retryable`,
`native_code`, `consequence`, `action`, with optional `reason_codes` and `count`.
Unknown causes, retryability or actions stay null. Native reason codes are distinct
from stable diagnostic codes and process statuses. Retain only safe qualified native
codes; credentials, private identities and raw native messages/responses stay out of
public diagnostics. Group repeated warnings by reason/component with counts and
bounded context. Capture helpers preserve an underlying public diagnostic while
identifying wrapper failure separately. JSON, text, GUI and existing exported result
representations preserve the same quality and diagnostic meaning.

The central process-status map is accepted success/warning **0**, operational/data
failure **1**, invalid invocation **2**, interruption **130**. Leaf-supplied integers
cannot override it or make an error envelope exit 0. Preserve specific errors such
as invalid argument, missing prerequisite, verified absence, auth failure, host lock
contention and unavailable browser; do not rewrite every failure as incompleteness.

## Publication and replay

Only Refresh writes the Temporary Query Cache. One accepted nonempty candidate
atomically replaces the leaf's one slot: records, scope, capture time, contract
metadata, warnings and quality evidence together. A qualified incomplete candidate
may replace a complete capture, with its gaps conspicuous. Persistence must finish
before success is reported. Failed acquisition, strict rejection, failed persistence,
interruption before commit and successful empty Refresh preserve the previous slot
and its original capture time. Empty Refresh explains that no replacement occurred.

Offline List retains acquisition gaps, warnings and timestamps; strict offline List
rejects incomplete coverage. Get and live List do not publish. List with Detail
combines List evidence with each selected Get's promised coverage; hard selected
Get failure fails the whole composition. Neither Get nor composition writes cache
or Duckdog. This policy adds no history, last-complete archive, merged captures,
automatic imports or relaxation of [Duckdog qualification](../../tools/leaf-dev/duckdog-import.md).

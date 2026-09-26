# Collection architecture refactor UAT

Observed: 2026-09-27
Scope: general
Status: snapshot

## Result and build

All six collection capabilities passed the production inquiry and private-cache
acceptance run: **2,010 assertions, zero failures**. Assertions include command
exit/output checks; this is not a count of distinct business scenarios.

The tested checkout was `refactor/collection-inquiry-architecture`, based on
`8797e05`, with the uncommitted snapshot-read, VA inquiry and command-registration
refactors. The run started at 2026-09-26 19:15:40 UTC and finished at
2026-09-26 19:26:02 UTC (2026-09-27 in Asia/Shanghai).

| Capability | Refreshed rows | Live rows | Refresh result | Detail verification |
| --- | ---: | ---: | --- | --- |
| Collection Transaction-Cost Configuration | 556 | 556 | Exit 0, complete | No detail command |
| Collection SLA Config | 55 | 55 | Exit 0, complete | All 55 cached details readable; live sample matched |
| Collection VA Capacity Row | 532 | 532 | Exit 0, complete | No detail command |
| Collection Clearing-System Configuration | 230 | 230 | Exit 0, complete | No detail command |
| Collection Card-Template Configuration | 152 | 152 | Exit 0, complete | No detail command |
| Collection VA Rule | 911 | 911 | Exit 1, expected partial publication | All 911 cached details checked: 840 readable, 71 refused; live samples verified |

Every cached scope had unique identities and the expected stable ordering.
Refresh/live identity sets agreed in all six scopes. Counts are observations,
not hardcoded invariants or evidence of backend transactional isolation.

## Method and data protection

The runner invoked the public `dogopencli.cli.main` entry point with normal CLI
arguments. It used the checkout's real restricted transport and the existing
headless Chrome on CDP 9222. Authentication checks passed before and after UAT.
No browser restart, login/logout, production configuration write, arbitrary
request, or arbitrary JavaScript entry point was used. Ports 9330–9340 were
not used.

A mode-0700 temporary directory held a private configuration and SQLite cache;
files were created with a restrictive umask. The private configuration declared
the six verified CDP sources, including sources absent from the operator's older
configuration, without modifying that configuration. Raw CLI output and filter
values were held in memory and were not written to logs or this report. The
private cache contains production records and is not a Git artifact.

The operator cache and its WAL existence/content fingerprints were unchanged
across the entire run. Every live list, filter and get query also preserved the
private cache fingerprint. Offline commands used an unreachable CDP setting on
9223, proving that the tested cached reads did not need a reachable browser.
Freshness rejection used TTL zero in the private configuration, then restored
TTL 72; no operator metadata or production data was changed.

## Argument and behavior coverage

All six list commands passed exact option-inventory checks, JSON/text help,
`--help` and `-h`, JSON/text describe, a cold-cache error, full live inquiry,
explicit refresh and full offline read.

| Surface | Executed checks | Result |
| --- | --- | --- |
| List `--limit`, `--offset`, `--all` | Default 100-row window; two-row windows at zero, last row, end and beyond end; `has_more`; complete ordering; invalid zero/negative/conflicting options | Pass |
| List `--live` | Complete full-scope acquisition and each domain filter; private cache unchanged | Pass |
| List `--require-fresh` | Fresh read; stale default read with stale metadata; strict stale rejection | Pass |
| List `--require-complete` | Complete-snapshot success; actual partial VA dataset rejection | Pass |
| List `--format`, `--fields` | Explicit JSON, projected table, identity projection, unknown-field omission; empty projection and invalid format rejection | Pass |
| Domain filters | Each exposed filter tested cached and live; exact local matches, repeated-value OR, cross-field AND before windowing, case/literal-star/whitespace/nonmatch behavior, empty-value rejection | Pass |
| SLA and VA `get --id` | Every refreshed ID read offline; absent ID rejection; missing/empty ID and list-only option rejection | Pass |
| Get `--live` | Readable SLA/VA samples matched cached details; refused VA sample returned `BUSINESS_QUERY_FAILED`; private cache unchanged | Pass |
| Get `--require-fresh`, `--require-complete` | Fresh success and stale rejection; complete SLA success and partial VA rejection | Pass |
| Get `--format`, `--fields` | Explicit JSON identity projection and projected table output | Pass |
| Refresh | All six production refreshes; help aliases and text help; unsupported live/display/positional arguments rejected | Pass |
| Get discovery | Help aliases, JSON/text help and JSON describe | Pass |

The domain filter inventory was reconciled against machine help:

- Collection SLA Config: `--business-line`, `--entity`, `--currency`, `--region`.
- Collection VA Capacity Row: `--va-rule-id`, `--bank-va-rule-id`.
- Collection Clearing-System Configuration: `--bank-location`, `--currency`,
  `--system-type`, `--system-name`, `--status`.
- Collection Card-Template Configuration: `--bank-location`, `--currency`,
  `--bank`, `--template-name`, `--template-id`, `--status`.
- Collection Transaction-Cost Configuration and Collection VA Rule expose no
  domain list filters.

Every filter had a usable production sample. Observed datasets constrain the
number of distinct filter values; differentiated edge cases remain covered by
synthetic SIT. This run covers every exposed option, not every possible
Cartesian combination of options or every future production value.

## VA Detail Refusal acceptance

The backend still refused 71 of 911 details. The refactored inquiry module
preserved [ADR 0010](../../adr/0010-collection-va-partial-detail-tolerance.md):

- Refresh published the list scope and available details, then returned exit 1
  with `INCOMPLETE_RESULT`.
- The resulting snapshot had `backend_complete=true` and
  `dataset_complete=false`.
- All 840 readable cached details returned their requested identities.
- All 71 refused cached details returned `INCOMPLETE_RESULT` with no data;
  none substituted a list row.
- An absent ID returned `NOT_FOUND`, because list coverage was complete.
- `--require-complete` rejected both list and get against the partial dataset.
- Explicit live get for a refused ID returned `BUSINESS_QUERY_FAILED`;
  refresh-only refusal tolerance did not leak into live get.

This is successful verification of the documented partial-publication contract,
not a claim that the backend defect is fixed or that all VA details are available.
Collection SLA retained its separate all-detail publication rule.

## SIT and unexecuted production failures

The preceding final repository run passed **951 tests and 23 subtests**, with
Ruff lint/format checks passing. All 66 static command help documents and handler
bindings matched the pre-refactor snapshot, including navigation order.

Authentication loss, HTTP 403, malformed responses, pagination drift,
interruption, lock contention, timeouts, cache corruption and preservation of
an older snapshot after non-refusal failure were not manufactured in production.
Those branches remain synthetic SIT evidence, including direct inquiry-module
checks that distinguish refusal replacement from HTTP-failure retention. An
empty production scope and unavailable nested-field shapes were not created.

This UAT covers the six collection capabilities affected by this refactor.
Payment production inquiries, authentication lifecycle UAT and wheel-install UAT
were not rerun in this session. No live backend write or forced failure was
needed to establish the reported acceptance.

## Review follow-up validation

The subsequent review cleanup shares refresh effects/constraints/errors between
payment and collection declarations, restores separate output dictionaries for
the moved cost/SLA/VA refresh nodes, and exposes VA result metadata through
`VaRuleSnapshot.meta()` instead of its internal cached query. Acquisition,
publication and refusal policy are unchanged.

The follow-up passed 111 catalog/help/inquiry-module tests and all 93 VA CLI SIT
cases. All 66 command help documents and handler bindings still match the
pre-cleanup catalog, including error and navigation ordering. The registration
test also proves that a new plugin appends its refresh declaration without
editing the existing compatibility-order reservations. Ruff lint/format,
documentation guard and whitespace checks passed.

The 951-test full-suite result and the 2,010 production UAT assertions above
belong to the original refactor (`bec1629`), not a new production run of this
cleanup. Production queries were not repeated for metadata encapsulation and
identical static command declarations. SLA inquiry extraction remains outside
the three selected refactor candidates; its existing all-detail policy is not
changed by the VA-specific inquiry module.

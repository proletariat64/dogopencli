# Payment rules implementation and acceptance

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Delivered boundary

#55–#58 implement independent same-bank-transfer, cost-reduction, retry and
bank-switch list/refresh/help/describe commands. The [frozen contract](2026-09-27-payment-rules-contract.md)
records endpoints, row identities, all 26 domain filters and acquisition limits.
#54 remains blocked by [reproducible detail identity mismatches](2026-09-27-payment-flow-rule-blocker.md);
no flow command or list-only substitute is registered. #59 is not complete.

## Production UAT

The public CLI ran against the existing authenticated dedicated Chrome session
on CDP 9222. A private configuration and SQLite cache under ignored `tmp/` were
used. Production raw responses and filter samples stayed out of logs and Git.
SHA-256 checks of the operator's original database, WAL and SHM files remained
unchanged after each capability and at the end. Live calls left the private
published cache unchanged. No production mutation or PTR action was performed.

All 424 assertions passed. Counts describe this observation, not fixed limits:

| Capability | Complete rows | Assertions for this capability |
| --- | ---: | ---: |
| same-bank-transfer | 34 | 56 |
| cost-reduction | 30 | 122 |
| retry | 89 | 155 |
| bank-switch | 46 | 90 |

The remaining assertion checks the operator cache at the end. After the review
fix below, bank-switch alone was repeated against a new private cache: all 91
assertions passed, including the final operator-cache check. Each domain flag
was exercised with an observed positive value, a synthetic nonmatch, repeated
OR and whitespace rejection in cached mode, then with the positive value live.
Bank-switch also exercised a combined five-field live/cached query. Production
samples do not prove absence of cross-child false matches; synthetic SIT covers
that adversarial condition independently.

## Argument and failure coverage

| Surface | Public CLI production/private-cache UAT | Synthetic public CLI SIT |
| --- | --- | --- |
| All 26 domain flags | Positive, nonmatch, repeat, whitespace; cached/live agreement | Independent literal mappings; case, literal `*`, spaces, comma handling, missing/null, array membership; bank cross-requirement/rule/target rejection |
| `--limit`, `--offset`, `--all` | Defaults, last/beyond window, conflicts, invalid values | 150-row default 100, full output; filter then sort then window then project |
| `--fields` | Identity projection, invalid empty value | Unknown field omission; quality metadata and nested content retained |
| `--format` | JSON/table, invalid format | Same plus offline help/describe JSON/text |
| `--live` | Full and every positive filter; cache unchanged | Refusal on cold and populated cache, no fallback/publication |
| `--require-fresh`, `--require-complete` | Fresh/complete snapshot | Stale TTL, incomplete metadata and corrupt snapshot rejection |
| Help, `-h`, `--help`, describe | List/refresh help and list describe with browser endpoint unreachable | Groups, aliases, excluded commands and refresh selectors |
| Refresh | Complete unique 34/30/89/46 rows | Empty/1/1000 boundaries; null/missing, wrong echoes, invalid totals, overflow/truncation, duplicates, malformed response, refusal |
| Safety and atomicity | Operator and live-cache hashes unchanged | Exact request allowlist; auth, timeout, interrupt, lock and SQLite publication failure preserve old snapshot; source isolation |

Unfiltered empty production scopes, scopes exceeding 1000 and production
failure conditions were unavailable or deliberately not induced. Those checks
use synthetic fixtures, not claims of production observation. Schema preserves
unknown fields and raw values; timestamp units, ratio scales and closed enums
remain unverified. Bank-switch returns complete source nodes including unmatched
children; cost-reduction returns group summaries, not complete version history.

## Verification gates

The full suite ran once: 1,142 passed and 23 subtests passed; two failures were
stale payment/refresh-payment help inventories missing the new rules group.
Both expected inventories were updated; the complete help and payment-rule test
files were rerun after that correction and the bank-filter fix: all 234 passed
(132 payment-rule cases and 102 help cases). No unresolved test failure remains.
Ruff lint/format and documentation guards passed. New rule modules and the changed collection configuration module
pass `ty`; CLI has 20 pre-existing diagnostics, reproduced on baseline commit
`2fa17e8` with identical diagnostic kinds and affected operations.


## Review

Standards review found no violations or actionable code smells. Spec review
found one boundary mismatch: source-network-only filtering admitted requirements
with no child rules. Removed that shortcut to match the frozen requirement/rule
correlation contract, corrected the adversarial expectation and passed all seven
focused bank-filter regressions. Independent re-review found no remaining issues.
The final wheel and source distribution built successfully; installation into a
separate environment passed 16 offline help/describe/excluded-command checks.


## PR #60 external review follow-up

Greptile passed for the initial `7d62456` head. Kimi's findings were checked
against code, the previous README and the complete issue comments:

| Finding | Decision |
| --- | --- |
| Frozen contracts absent from issues | Incorrect as stated: full contracts were posted before implementation on #55–#58 at 01:46 UTC on 2026-09-27. The issue bodies and unchecked completion lists were stale; synchronized those with the existing contract comments and PR evidence, keeping the issues open until merge. |
| README rewrite exceeds scope | The user separately requested the complete rewrite. It remains authorized. |
| Two outstanding external UAT dependencies dropped | Confirmed. Restored logout UAT scope confirmation and the default-launcher login → payment-cost-refresh production re-verification. Existing-session rule queries and empty-profile CDP smoke do not close those items. |
| `peer` hides capability and pagination meaning | Renamed to `is_same_bank_transfer`; introduced explicit `first_page` instead of converting a boolean to a page number. The verified same-bank contract remains one coherent variant; no configurable combinations or new enum are needed. |
| Shared help groups depend on tuple position | Bound ownership to the `same-bank-transfer` slug, independent of capability ordering. |
| Collection validation delegation | Retained the small adapter for shared cached validation. A new Protocol would not improve behavior or remove the need for collection validation. |
| Description branches | Retained the four small capability-specific schema branches; no additional abstraction is justified by this batch. |

Before the refactor, 21 boundary/identity/request-contract tests passed. The 12
public list-help, refresh-help and describe documents are byte-equivalent after
canonical serialization; reversing the capability tuple keeps group ownership
unchanged. This follow-up does not change endpoints, query semantics or public
schemas, and does not perform login/logout or production mutations.

Final follow-up verification: all 234 payment-rule/help tests passed; Ruff lint
and format, focused `ty`, doc-guard and its nine self-tests passed.

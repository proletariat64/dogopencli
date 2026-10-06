# Liquidity Batch H acceptance: rule-status enabled, quote-groups blocker reaffirmed

Observed: 2026-10-06
Scope: general
Status: snapshot

Implementation scope: spec [#122](https://github.com/proletariat64/dogopencli/issues/122)
under parent [#72](https://github.com/proletariat64/dogopencli/issues/72), with tickets
[#123](https://github.com/proletariat64/dogopencli/issues/123) (rule-status enablement),
[#124](https://github.com/proletariat64/dogopencli/issues/124) (quote-groups coverage
proof attempt) and [#125](https://github.com/proletariat64/dogopencli/issues/125)
(documentation closeout). Work merged into the integration branch `feat/batch-H`.
This document records batch acceptance evidence only; production CLI UAT was not
performed this round and is explicitly not claimed.

## #123: rule-status enabled

`liquidity operations rule-status list` is now a supported bounded list over the
TransferRunOverview summary inquiry:

- Required paired UTC `--trigger-from`/`--trigger-to` bounds
  (`YYYY-MM-DD HH:mm:ss`, inclusive, equal endpoints allowed), rejected before
  browser access when missing, malformed or reversed.
- One counted single response: pageSize 5000, rowStart 0, exactly one request;
  no paging loops, offsets, dedupe or fallback.
- Hard gates before output or cache publication: overflow (count or array over
  5000, advising a narrower trigger range), shortfall, extra rows, duplicate
  native IDs, invalid or missing count, wrong tenant and out-of-scope trigger
  timestamps all fail strictly; ADR 0019 does not lower these gates.
- Lossless positive-integer native `id` as public identity; native
  executeStatus/createdOrder/orderStatus distinctions and nullable
  realTriggerTime preserved; timestamps are UTC epoch milliseconds; amounts,
  account aliases and free text are excluded.
- Independent exact profile/tenant/trigger-scope cache: refresh publishes under
  the precise scope, live leaves cache bytes unchanged, failures preserve prior
  cache bytes, and a genuinely empty successful scope caches truthfully.
- Getter and queryDetailed expansion remain unsupported.

The verified native contract and first-enable evidence are recorded in
[Batch H rule-status contract](2026-10-06-batch-h-rule-status-contract.md); the
Batch F F2 deferral record carries a superseded continuation note. The full
repository suite passed **2597 tests** at merge, with Ruff lint and format
clean.

## #124: quote-groups blocker reaffirmed

Eight controlled read-only probes of `/queryQuotationGroup.json` on the
authorized profile (empty-object replays plus pageSize/rowStart combinations
using only native-caller fields; no invented filters) all returned the
identical 54-record identity set with no server-authoritative total and no
progressing or terminating paging protocol. The blocker stands: `investment
quote-groups list` stays unsupported with the existing `total-unverified`
deferral reason. Evidence is the 2026-10-06 continuation section of the
[quote-groups investigation](2026-10-04-liquidity-batch-a-quote-groups-investigation.md).

## #125: documentation closeout

This record; the Batch H research reports
[remaining-list PRD crosscheck](2026-10-06-remaining-list-prd-crosscheck.md) and
[remaining-list current probes](2026-10-06-remaining-list-current-probes.md)
are imported into the repository verbatim; the Batch F F2 deferral record is
annotated as superseded. The `未发布` CHANGELOG entry records the batch.

## Explicitly not done

- Production CLI UAT for the enabled rule-status leaf: **not claimed**. It
  remains a future serial per-leaf production acceptance on the authorized
  profile (known nonempty expanded trigger scope, successful empty current-day
  scope, equal-endpoint point scope, disconnected offline equality, live
  no-write, failure/cache preservation).
- Parent [#72](https://github.com/proletariat64/dogopencli/issues/72) is **not
  closed**; remaining unsupported leaves stay discoverable but non-executing.
- No release: the `未发布` CHANGELOG entry accumulates and the version remains
  v0.2.8.

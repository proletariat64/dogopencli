# Bank reference inquiry

`dogopencli liquidity list reference.banks` reads maintained bank reference
records. `bankId` is the native record identity; names, SWIFT codes, `cityCode`
and `state` retain their backend values. Unknown fields, null, empty strings,
zero and exact JSON decimals remain intact. This package is delivered separately
from the four bundled pilot identities.

The native inquiry is GET `https://iliquidity.alipay.com/queryParaBank.json`.
Its authenticated entry is
`https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt`.
Only `tntInstId=GUAPW3SG` and JSON-encoded `paraBankVO` are sent. The VO contains
`tntInstId=GUAPW3SG`, zero-based `rowStart` offsets and `pageSize=5000`.
Success requires `resultFlag=true`; rows are `result.bankVoList` and the fixed
nonnegative integer total is the top-level `count`. A nested `result.success=false`
is a business failure. This is an inquiry, with no configuration mutation.

`--country SG --country US` selects rows whose native `cityCode` equals either
value. Matching is exact and case-sensitive. Repeated values do not duplicate
rows. Selection happens locally after full acquisition for live list and against
the full saved snapshot for offline list. It never changes native request scope.
Refresh retains the complete native acquisition even when a country is supplied.
Display limits do not truncate collection. Live list does not publish a snapshot.

The collector checks fixed totals, empty pages before the reported end, page
capacity, identities and duplicate content. Duplicates cannot prove completeness;
the shared host applies usable-incomplete or strict policy. Empty refresh, failures
and strict refusals preserve the previous snapshot. No getter is exposed.

## Provenance and verification boundary

The fixed historical reference is release `v0.4.3`, commit
`a7e5c5ead675487646eb9a53d73ec9e0aeb944f9`,
[`REFERENCE_BANKS` and local-filter declaration](https://github.com/proletariat64/dogopencli/blob/a7e5c5ead675487646eb9a53d73ec9e0aeb944f9/src/dogopencli/plugins/liquidity/leaves.py#L1321).
This was inspected outside the repository; no historical module is imported or
retained in this package. The adapter uses only current neutral host contracts.
The knowledge-base graph query for `queryParaBank` did not establish the native
contract; the pinned descriptor supplies historical provenance only.

Controlled CDP integration tests exercise actual directory and ZIP installation,
the public CLI, native multi-page responses, precision, country selection,
refresh/offline behavior and cache preservation. They do not qualify current
production access or nonempty data. Production and artifact acceptance are recorded
by the batch #257 owner, separately from these automated checks.

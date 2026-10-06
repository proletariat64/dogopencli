# Liquidity batch A quote-group completeness investigation

Observed: 2026-10-04
Scope: general
Status: snapshot

Specification: [#87](https://github.com/proletariat64/dogopencli/issues/87).
Investigation ticket: [#92](https://github.com/proletariat64/dogopencli/issues/92).

The investigation is complete with a first-enable blocker. The
`investment quote-groups list` leaf remains unsupported. Current nonempty
responses establish record structure and offset behavior, but do not establish
full population coverage. The two mandatory batch A lists have independent
acceptance gates; this optional leaf does not change their denominator of two.

## Native caller and current source

The current production UI bundle was compared with the saved native bundle and
has the same SHA-256 digest. In that source, the inquiry wrapper calls
`POST /queryQuotationGroup.json` with JSON encoding. Its list caller sends
`pageSize` and `rowStart`; the initial request uses `pageSize=10, rowStart=0`.
Page navigation calculates `rowStart=(current-1)*pageSize`. The caller reads
response `data` for records and `totalCount` for the displayed total.

Native search controls also supply quotation-group ID, quotation-group name,
bank ID and status selections. These controls establish UI vocabulary only;
this investigation does not certify their server filtering semantics or expose
new CLI parameters. The inquiry wrapper is separate from the adjacent add and
update wrappers; those mutation actions are outside this CLI's scope.

## Current nonempty response evidence

Two read-only requests used `pageSize=10` and `rowStart=0` or `rowStart=10`.
Both succeeded and returned 54 records. The complete record arrays were equal,
including record identities and content. The success envelope contains `data`
as an array, with no `totalCount`, other reported total, or verified terminal
marker. The historical response also contained 54 records without a total;
that historical count was a sample size, not a completeness claim.

| Observation | Current result | Implication |
| --- | --- | --- |
| Offset zero | 54 records | Response exceeds the requested display size |
| Offset ten | Same 54 records and content | Requested offset does not advance this observed response |
| Reported total | Absent | No source count can be compared with arrival count |
| Native ending protocol | Unverified | Neither a short-page rule nor single-response completeness is established |
| Raw / unique record IDs | 54 / 54 in each response | Identity uniqueness within the sample is established; coverage is not |

Repeated identical responses do not prove that these records are the whole
population. Returning more than `pageSize` does not prove a native full-response
contract either. The CLI must not manufacture a total, deduplicate repeated
responses into a complete capture, or declare completeness from these counts.

## Identity and settings semantics

The observed fields distinguish record identity from logical quotation-group
identity and version:

| Field or tuple | Observed type | Distinct values in 54 records |
| --- | --- | --- |
| `id` | string | 54 |
| `quotationGroupId` | string | 48 |
| `version` | integer | Four version values |
| `(quotationGroupId, version)` | string / integer | 54 |

The repeated logical group IDs therefore cannot serve as unique row identities.
The native record `id` is the candidate identity; tenant, cross-capture and
variant scope still need verification before enablement. The unique group/version
tuple describes this sample and does not replace native identity with an
inferred key. No record values or tenant identifiers are published here.

This leaf keeps its existing `settings` classification. Group definition,
version and status are configuration evidence. The observed string fields
`gmtCreate`, `gmtModified` and `lastModifiedTime` do not establish a runtime
business observation time. Refresh time would remain `fetched_at`, independently
of those native configuration timestamps.

Potential business projection fields are `id`, `quotationGroupId`,
`quotationGroupName`, `bankId`, `status`, `tntInstId`, `version`, `gmtCreate`
and `gmtModified`. Their publication remains gated on a verified contract.
Contacts, contact lists, operator identities, free text, attachment paths/URLs
and operation-history content are excluded from public evidence and fixtures.

## Blocker and continuation conditions

The first-enable blocker is the absence of an authoritative full-response
contract or a working, verified pagination ending protocol. Current offset
requests do not demonstrate progress and the response has no reported total.
This is an investigation conclusion, not production UAT of an enabled list.

Continue only when native evidence establishes one of the following:

- An authoritative single-response protocol establishes that the successful
  response covers the declared scope without truncation or hidden paging.
- A native paging protocol advances records and exposes a trustworthy reported
  total or explicit terminal condition. Validate raw arrival count, unique native
  identities, stable count units, and absence of duplicates, omissions or
  identity conflicts across a representative complete acquisition.

Then verify tenant/variant identity, settings field meanings and any public
filters. Enablement also requires registered CLI refresh/offline comparison,
complete empty capture, live cache isolation, partial/strict behavior, hard-failure
cache preservation, retention and independent production acceptance. None of
these conditions is waived by a nonempty sample or by this report.

No new quote-group list/get/history executor or cache is introduced by this
investigation. Existing unsupported discovery remains the user-visible gate.

## Continuation 2026-10-06 (batch H coverage proof attempt)

Continuation ticket: [#124](https://github.com/proletariat64/dogopencli/issues/124)
under specification [#122](https://github.com/proletariat64/dogopencli/issues/122)
(Target 2). A bounded read-only proof attempt ran on 2026-10-06 against the
dedicated authenticated session, mirroring the shared CDP transport mechanism
from one own temporary target on the liquidity entry origin. Only aggregates
were recorded; no raw production rows left the browser.

Eight requests were issued, one at a time, using only fields with native caller
evidence (the empty object, and `pageSize`/`rowStart` as used by the native
list caller); no invented filters: `{}` twice (stability), `{pageSize:10,
rowStart:0}`, `{pageSize:10, rowStart:10}`, `{pageSize:10, rowStart:50}`,
`{pageSize:5, rowStart:0}`, `{pageSize:5, rowStart:5}`, `{pageSize:100,
rowStart:0}`.

Every request returned HTTP 200 with the same envelope keys (`data`,
`detailMessage`, `errorCode`, `errorContext`, `errorMessage`, `success`), no
`totalCount`, `total`, or terminal marker. Every response carried 54 records:
54 unique native `id` values, 54 unique `(quotationGroupId, version)` pairs,
48 distinct logical `quotationGroupId` values, four version values. The record
identity set was identical across all eight responses (single shared id hash;
54/54 pairwise overlap), including across every `pageSize`/`rowStart`
combination. Paging fields do not advance, narrow, or terminate this endpoint;
repeated identical pages demonstrate no progression.

The blocker is reaffirmed unchanged: no server-authoritative total or
completeness signal exists in the response envelope, and no genuinely
progressing paging/ending protocol was observed. The 2026-10-06 identity
structure (54 ids / 54 group+version pairs / 48 logical groups) matches the
prior evidence and remains a sample description, not a coverage claim. The
`investment quote-groups list` leaf stays unsupported with the existing
`total-unverified` deferral reason, and the continuation conditions above still
govern any future enablement.

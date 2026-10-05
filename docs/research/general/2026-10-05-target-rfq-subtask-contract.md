# TARGET_RFQ subtask list contract

Observed: 2026-10-05
Scope: general
Status: snapshot

Native inquiry evidence is described in issue #112. This document covers
Liquidity `investment rfqs list`, fixed TARGET_RFQ and explicit dates.
Implementation has fake CDP acceptance; independent production CLI UAT is pending.

The inquiry sends a JSON POST to the allowlisted Liquidity origin at
`/rfq/subInquiryTask/querySubInquiryTask.json`. `rowStart=0`, `pageSize=5000`
and `inquiryType=TARGET_RFQ` are fixed transport values. Paired public
`--from-date/--to-date YYYY-MM-DD` values must be valid and ordered, and map
to native `inquiryStartDate/inquiryEndDate` in YYYYMMDD. No optional product,
status, parent, task, type or page-width filters are accepted.

A successful envelope requires boolean `success=true`, an object array at
`data.data` and nonnegative integer `data.totalCount`. One response is complete
only when arrivals, unique native `inquirySubTaskId` and total all agree. Safe
nonempty partial results follow ADR0019; strict mode rejects them without
publishing. Empty rows with positive total, invalid envelopes, authentication,
permissions, transport errors, conflicting identities and wrong type echoes
are hard failures. There is no offset collection, repeated acquisition or
supplementation from another type. Successful empty rows and native total zero
are a complete empty response. Backend 099 is a failure.

Identity is a nonempty native string `inquirySubTaskId` in the tenant,
TARGET_RFQ and exact date scope. `inquiryTaskId` remains a parent reference:
two distinct subtasks sharing a parent remain separate. No quotation session
is derived from a parent identifier.

The business projection retains `inquirySubTaskId`, `inquiryTaskId`,
`inquiryType`, `productType`, `currency`, `tenor`, `redemptionFeature`,
`inquiryStatus`, `quotationStatus`, `winStatus`, `quotedNum`, `inquiryNum`,
`winNum`, `inquiryStartTime`, `inquiryEndTime`, `modifyTime` and `processStatus`.
Personnel, memo, processId, other free text and unknown fields are excluded.
Allowlisted business values remain unchanged, including null, blanks, zero,
negative values, precision and unknown states. There is no business arithmetic.

Source timezones and exact native boundary semantics remain unknown.
Native source timestamps stay separate from capture time. Unknown timestamp
interpretation is not used to filter rows or infer coverage. The history
profile and `rfq-target-subtasks-v1` schema retain captures by fetch time,
with exact date/type scope and no cross-range fallback. Refresh publishes
atomically; offline reads never need the browser; live reads never write SQLite.
Existing quote, product, strategy and native detail caches remain independent.

The issue records a fresh native nonempty TARGET_RFQ result of 1/1 over
2026-01-01 through 2026-10-05. This does not establish future large-volume
pagination behavior. FULL_RANGE_RFQ still returns 099 and remains outside
scope, together with unbounded history and RFQ parent getters.

Local acceptance uses public CLI calls, fake CDP and temporary real SQLite.
Production CLI UAT must independently refresh a complete nonempty authorized
range, validate native identities and all projection fields, read the same
capture offline, and show live leaves SQLite unchanged. Fake CDP and historical
native probes do not satisfy that UAT requirement.

# Realtime network detail output boundary (B02)

Accepted implementation contract for [specification #173](https://github.com/proletariat64/dogopencli/issues/173)
and [tracker #165](https://github.com/proletariat64/dogopencli/issues/165).
This boundary is the input to B03 #166; B02 does not alter external datasets.

`liquidity network realtime get --network-id <native-id>` remains an online,
inquiry-only settings command. Its `data` is one selected network object.
The existing 26 root fields retain their native names, values, presence and
nulls. Two reserved CLI fields are added after the root projection:
`operationHistory` and `routeDetails`. A collision with either reserved name
in the raw root is an `INVALID_RESPONSE`, including a native null collision.

## Root and associations

The root keeps `id`, `routeId`, `version`, `scene`, `fundAction`,
`debitAliasName`, `debitBankId`, `debitCurrency`, `debitLegalEntityCode`,
`creditAliasName`, `creditBankId`, `creditCurrency`, `creditLegalEntityCode`,
`clearingNetworkName`, `clearingNetworkType`, `networkStatus`, `runStatus`,
`processStatus`, `operationCalendar`, `operationDateType`, `operationTime`,
`operationTool`, `singlePaymentLimit`, `timeZone`, `gmtCreate`, `gmtModified`.
`operationTime` and `singlePaymentLimit` are never filled from route values.
Missing fields remain missing. Source times and configuration versions remain
native; capture time is recorded separately.

History uses the verified singleton credit/debit alias arrays and fundAction
from a selected REALTIME root, through one private JSON POST inquiry. Its native
success array contains network configuration versions. Each row uses the same
26-field safe projection, retains its independent native `id` and integer
`version`, and must match the requested aliases/action and REALTIME scene.
Native identity conflicts and tenant contradictions are hard failures.
The request does not pin root ID or version. The selected root need not appear
in the history array. A matching ID with changed projected configuration is
reported as `SOURCE_CHANGED`; neither read replaces the other.

No native history total or pagination/exhaustion proof is available. Successful
history arrays, including empty arrays, are usable incomplete results with
`HISTORY_COVERAGE_UNPROVEN`. Unknown root caller context produces null history
with an explicit unverified component status; it sends no speculative request.

Route detail reuses the existing account-context quota validation and performs
one GET inquiry for the selected root's routeId, debitAliasName and verified
application tenant. A present native null or empty routeId establishes caller
inapplicability: routeDetails is null and no inquiry occurs. Missing or malformed
route/account context remains unverified; it is never replaced by the credit
alias or a global route list. Native context echoes, when supplied, must match.
Absent echoes are explicitly recorded; request context does not fabricate native
fields. Both dynamicQuotas and staticQuotas arrays are required. Native order,
blank/repeated quotaId, currencies, markers, numeric precision and nulls remain.

The safe route projection includes:

- Dynamic members: dateRange with begin/end; individualLimit, remainLimit and
  totalLimit with currency/hasLimit/limit.
- Static members: bic, chainId, currency, individualLimit, quotaId, quotaSide,
  serviceWindowIntersection, tokenName, tokenTransactionType, totalLimit,
  updateTimeSliceConfig, usedQuota.
- Window groups: timeSliceGroupId and timeSliceInfoList.
- Time slices: beginFromPreviousDay, beginTime, endTime, holidayTypeCode,
  timeSliceId, timeUnit, timeValue, timeZone.

No arithmetic, flattening, timezone conversion or sentinel reinterpretation is
performed. Native result.count is preserved with unknown units, independently
of each quota member count; it does not determine array coverage. The successful
scoped aggregate follows the existing route-quota coverage contract. A successful
pair of empty quota arrays is an empty scoped result, independently of history
coverage. Public route-quota behavior is unchanged.

## Quality, provenance and storage

`meta.components.network`, `.operationHistory` and `.routeDetails` each expose
status, applicability, identity or contextual binding, request_scope,
native_contract, captured_at, returned_count, reported_count, count_unit,
complete and reasons. Route adds member_counts, reported_count_unit and
native_context_echo. History adds selected_root_relation and its pagination
limitation. Unqueried components have no fabricated capture time or counts.
Network identity, route context and history record identities are distinct.

The top-level returned_count and matched_total remain one. Top-level
completeness includes every applicable component. Default safe incomplete output
warns and exits zero; `--require-complete` returns `INCOMPLETE_RESULT` with
`data=null` and retains component diagnostics. Authentication, transport,
business, malformed payload and identity failures withhold all business data.
All component inquiries share the existing bounded acquisition deadline and
retry policy, with at most one history response and one route aggregate.
The sequential reads do not establish an atomic snapshot.

JSON fields selection does not change quality. Default table output includes
association JSON cells and always displays component diagnostics, including
when fields selection hides those cells. Get never writes cache; list and
refresh never acquire these associations. B03 can store the 26-field root and
associations separately using component request scope and provenance. It must
retain history versions with distinct IDs and distinguish unknown/null,
inapplicability, successful empty arrays, and incomplete coverage. B02 creates
no independent association dataset or historical cache.

Dynamic effectiveness/success statistics, personnel, free text, attachments and
action payloads remain excluded. Production observations and public CLI UAT are
separate evidence layers; historical sample counts are not permanent contracts.

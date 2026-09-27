# Collection account-isolation inquiry contract

Observed: 2026-09-27
Scope: general
Status: snapshot

Focused verification for #51 reused the completed
[menu survey](2026-09-26-collection-menu-deep-survey.md).
The DI browser specification and launcher were read; the existing authenticated
dedicated headless Chrome used CDP 9222. Temporary targets were closed. Unknown
business requests were blocked; only native Query and verified inquiry replay
were executed. No raw rows, account values, credentials or HAR were saved.

## Native query and schema

The native page at
`https://ifundcontrol.alipay.com/productOperation/collectionProductManagement/networkConstruction/businessAccount`
issued POST JSON to
`https://ifundcontrolprodops.alipay.com/api/virtualAccountRuleConfig/search`
with `pageNo=0,pageSize=10`. Query was observed after page initialization.
Credentials remain browser-managed. Current loaded static sources were
`umi.3f8f4633.js` and `d757b557-async.95fe150e.js` under
`https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001251366/`.
The service uses POST search; the component binds columns/filters to the fields
below, uses rowKey=id, and reads `data.businessDataList` and `data.totalCount`.
Create/detail actions were not executed.

Successful HTTP 200 responses contain boolean `success=true` and a `data`
object with `businessDataList`, integer `pageNo`, `pageSize`, `totalCount`
and `totalPageNo`. Envelope messages and trace fields are not business rows.

| Field | Observed JSON types | Meaning / filter |
| --- | --- | --- |
| id | string | Unique opening-rule row identity; --opening-rule-id |
| businessCategory | string, null | Business line; --business-line |
| businessRegionScope | string | Business region; --business-region |
| customerTags | string | Customer tags; --customer-group |
| sceneCode | string | Scene code; --scene-code |
| creditArea | string | Collection region; --collection-region |
| currency | string | Collection currency; --currency |
| regionType | string | Transaction type; --transaction-type |
| businessEntity | string | Business entity code |
| finInstCode | string | Institution code |
| lastOperator | string | Last operator |
| gmtCreate, gmtModified | integer | Raw timestamps; units/timezone unverified |

IDs were 15- or 19-digit strings. Keep them as strings, including future leading
zeros; sort lexically. Identity is required; optional/unknown fields remain raw.
This is an account-isolation configuration, not an individual account or bank VA rule.

## Complete acquisition and empty shape

Two independent first-page size-1000 reads each returned 99 rows, 99 distinct
nonempty IDs and totalCount=99, with identical ordered IDs. A size-10 sweep
returned the same 99 unique IDs. Counts are observations, not invariants.
`totalPageNo` remained zero even for nonempty results; it is not a usable page
count. A pageNo=1,size=1000 beyond-end query returned success=false.

Frozen acquisition: one unfiltered request with pageNo=0,pageSize=1000.
Require correct page/size echoes, rows=totalCount and unique string IDs.
Overflow, truncation, invalid metadata, duplicate identities or refusal fail
without publication. No speculative next page or alternative page-size fallback.

Two independent nonmatching filters (numeric-string id and sceneCode) returned
success=true, data.businessDataList=null and all four pagination fields zero.
Review correction (2026-09-27): filtered evidence does not establish the meaning
of that shape on the unfiltered acquisition path. Reject null/zero responses
with INVALID_RESPONSE and preserve any prior snapshot. This supersedes the
original normalization rule. Missing list/data or contradictory metadata also
fail. A conventional empty array with correct request echoes and zero total
is accepted. An unfiltered empty production scope was unavailable; empty-array
acceptance remains synthetic-only, not a production observation.

## Frozen filter semantics and source

All eight proposed filters are included with the mapping above. They run locally
over the complete scope and use case-sensitive whole-string equality. Repetition
within a field is OR; different fields are AND. Asterisk is literal, missing/null
never match, whitespace-only input rejects, and accepted input is not normalized.
Filters precede lexical identity sorting, display windows and projection.

Every field had a nonempty string sample for positive verification. Backend
positive probes for id, businessCategory, businessRegionScope, sceneCode,
creditArea and regionType matched the local exact counts. customerTags returned
26 rows versus 9 exact local matches; currency returned 14 versus 11. This
proves backend behavior differs, not its full matching algorithm. 42 rows had
commas in customerTags, 3 in currency; 7 currency strings contained asterisks.
The CLI deliberately does not split comma strings or emulate backend membership,
substring or wildcard semantics. Users supply the exact returned scalar value.

Source: `[sources.collection_account_isolation] kind="cdp"`.
Capability: `collection.account_isolation.list`; scope: `all`; namespace:
`collection.account_isolation.list:all:cdp`. Defaults remain offline, 100 rows,
JSON and 72h configured shared TTL. Live never publishes/falls back; unfiltered
refresh atomically publishes complete scope only. List/refresh/help/describe
are included; detail/get, relationship queries, joins and mutations are excluded.

Only pageNo/pageSize with their frozen values enter the CLI request allowlist.
Schema, enums and time units beyond the observed evidence remain open; no derived
business calculations, closed enums or status normalization are introduced.

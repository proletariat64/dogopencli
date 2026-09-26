# Collection card-template inquiry contract

Observed: 2026-09-27
Scope: general
Status: snapshot

Focused verification for #45/#46, starting from sections 6–7 of
[the completed collection survey](2026-09-26-collection-menu-deep-survey.md).
No repeated menu discovery. Dedicated existing headless Chrome/CDP 9222,
auth check authenticated and healthy. The required DI browser specification
and its launcher implementation were read; their port default was not used.
Temporary targets were closed. No raw rows, identifiers, tokens or responses
were saved. Only sanitized structures and aggregate counts are recorded here.

## Native inquiry and static evidence

Native Search on `https://ifundbossportal.alipay.com/voucher/CollectionCardTemplateConfig`
issued `POST https://ifundboss-api.alipay.com/ivostro/api/cardTemplate/pageList.json`
with JSON `pageNo=1, pageSize=20`.
The browser carries `ctoken` in the query; credentials stay browser-local.
Replaying only `pageNo/pageSize` was also verified against the full scope.

Native Search was traced through the actual loaded component
`ca1d2eae-async.04d83749.js`
and service module `4636116f`, under
`https://renderoffice-intl.alipayobjects.com/p/yuyan/180020010001284167/`.
UI raw-field bindings were checked against the response schema and positive
filter probes. Required currency metadata GETs `/api/common/currency.json`
and `/api/common/getCurrency.json` were checked in `umi.bfbf5fa6.js` before
being allowed. Unknown requests were intercepted. Add/edit/offline/delete,
export, detail and relationship actions were never executed.

Success is HTTP 200, boolean `success=true`, `resultDataList` array,
integer `pageNo/pageSize/totalCount`; empty error strings, `data=null` and
trace/error-context fields are present. Only business rows enter CLI output;
raw messages and envelope trace information are not emitted or cached.

## Complete acquisition and identity

- Native 20-row queries report a fixed total in this observation.
- Two 1000-row first-page reads each returned 152 rows,
  152 distinct nonempty string `id` values, identical ordered IDs,
  and `totalCount=152`. This count is not an invariant.
- A full 20-row sweep collected 152 rows with
  152 unique IDs; identity-set agreement with the
  large query: true.
- A request for page 2 at size 1000 returned page 1 with the entire first
  page again. A filtered one-row scope at size 1 also returned page 1 when
  page 2 was requested. Beyond-end pages clamp to the valid page range;
  do not use an extra empty page as a termination signal.

Frozen acquisition: **one unfiltered page**, `pageNo=1, pageSize=1000`,
through the shared collector. Accept only when `len(rows)==totalCount`,
all IDs are nonempty strings and unique, size echoes 1000, and page echoes 1.
An exact 1000-row scope succeeds only with total 1000 and unique IDs.
Any total exceeding returned rows or 1000, duplicate, wrong echo or malformed
response fails before publication. Do not introduce multi-page fallback or
reuse VA capacity's running-total behavior. If the scope outgrows this
verified single-page capacity, fail explicitly and reverify a larger request
or stable pagination before extending the contract. This bounds capacity;
it never silently publishes a subset.

A row is one backend collection card-template configuration record, identified by
string `id`, not by a guessed composite of display fields. Sort IDs lexically
as strings, preserving leading zeros; filter before sorting/windowing.

## Row schema

All observed rows had the following keys (no missing/null fields observed).
Only identity is required by the CLI; retain other fields and unknown
extensions without imposing the observed all-present shape.

| Raw field | Observed JSON type |
| --- | --- |
| `cardTemplateItemList` | array |
| `creator` | string |
| `gmtCreate` | integer |
| `gmtModified` | integer |
| `id` | string |
| `lastOperator` | string |
| `remark` | string |
| `status` | string |
| `supportedCountry` | string |
| `supportedCurrency` | string |
| `supportedFinancialInst` | string |
| `templateName` | string |
| `templateType` | string |

Timestamp values were integers; epoch units/timezone remain unverified and
are preserved raw. Observed statuses: `VALID`, `AUDITING`, `INVALID`, `REJECT`.
The UI additionally offers INIT/AUDITING/REJECT/VALID/INVALID as configuration
lifecycle states; no closed enum validation or inferred normalization is
introduced. Future raw values remain representable and filterable.

`templateName` is the row field behind the UI CardTemplateName label;
`cardTemplateName` is the server filter name, not a returned field.
All observed `cardTemplateItemList` arrays were empty, so nested element
schema is unverified. Preserve arrays and future nested values as received;
never advertise detail coverage. RelatedBankVaAccountRule invokes a separate
query and is not a returned list field. Detail/relationship fetches are deferred.
The historical PRD (graphify query followed by source reading),
`收款产品-运营能力-收款信息及卡模板模型-2026-04-19-[154650137].md`,
defines the template as collection-information field selection rules; it is
context, not evidence for current detail APIs or complete template contents.

## Frozen filters

All candidates are included as local exact, case-sensitive string matches
on the fields below; repeated same-field values OR, different fields AND.
`*` is literal, including any multi-currency `*` value. Reject empty or
whitespace-only values, never trim/normalize accepted values. Missing/null
never match. Do not interpret local filters as backend substring/wildcard
queries or a closed enum.

| CLI flag | Raw row field |
| --- | --- |
| `--bank-location` | `supportedCountry` |
| `--currency` | `supportedCurrency` |
| `--bank` | `supportedFinancialInst` |
| `--template-name` | `templateName` |
| `--template-id` | `id` |
| `--status` | `status` |

For every field, a native-service positive filter probe returned only exact
matching rows with a count equal to local filtering of the full snapshot.
A nonmatching sentinel returned success=true, pageNo=0, pageSize=1000,
totalCount=0 and an empty resultDataList. Card-template name requests use
`cardTemplateName`; all other server filter keys equal the mapped raw field.
Broader server substring/case/wildcard semantics were not claimed or needed:
production CLI requests expose no backend filters.

## Empty scope, errors and isolation

Empty unfiltered scope was not available on this account. Adjacent verified
empty-filter behavior supports a conservative explicit shape: success=true,
size=1000, total=0, empty list, pageNo=0 or 1. Any other empty-page echo,
zeroed size, refusal or ambiguous shape fails. Exercise genuine empty scope
and auth/browser/refusal/malformed/lock/timeout/interruption synthetically.
Do not invent backend-specific error-code meanings.

Use `[sources.collection_card_template] kind="cdp"`, capability
`collection.card_template.list`, scope `all` and namespace
`collection.card_template.list:all:cdp`. Shared TTL stays 72h by
default. Refresh is unfiltered and atomic; live reads never publish.
Final list inventory: eight common options plus the 6 filters above.
Refresh takes no selectors. Help/navigation/describe are offline.

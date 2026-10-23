# Forecast record inquiries

Read this guide when changing `liquidity.forecast.results` or
`liquidity.forecast.accuracy`. Public selectors and output fields are described
by each installed leaf's help/describe. Both Lists compose every acquired parent
before the host applies display `--offset` and `--limit`.

## Results and record curves

The base inquiry is `GET /bankCashForecastRecordQuery.json`, tenant `GUAPW3SG`,
with inclusive native value-date and creation-clock bounds, optional literal
account aliases, native `id`, offset width 5000 and native `result.count`.
The general collection provider retains its existing completeness checks.

Each parent requires `GET /bankCashForecastRecordCashFlowQuery.json`. Its outer
`tntInstId` is fixed; serialized `bankCashForecastRecordCashFlowVo` contains
`tntInstId`, `forecastRecordId` from parent `id`, `baseBalance` from parent
`openBalance`, and that parent's `currency` and `valueDate`. Missing or
unqualified bindings fail before the child request. `forecastBalance` is not
an opening-balance substitute.

`cashflow_curve` preserves the entire native `result.alias` object. Its
`allDate`, `expectBalance`, `expectInflow` and `expectOutFlow` arrays must contain
native strings and have equal lengths. Preserve order, duplicate points,
precision and unknown fields. Four empty arrays are a successful empty curve;
missing arrays and unequal lengths are malformed responses. Neither 49 points
nor a 30-minute cadence is a contract.

The curve is a request-scoped aggregate without a manufactured native identity.
Validate provided binding echoes; keep absent echoes absent. Evidence records
the parent/request association, successful curve requests and observed point
counts independently of parent coverage. Native aggregate total stays unknown.
The operation shares at most 10000 physical requests and 1800 seconds across
base collection, curves, retries and probes.

## Accuracy and comparison occurrences

Keep one literal account alias and one native creation-query day. `record-date`
does not select returned `valueDate` or `baseValueDate`. At most 100 base records
are accepted before child queries. Shared bounds remain 303 physical requests
and 300 seconds.

`GET /bankCashForecastRecordAccuracyQuery.json` supplies raw parent context.
`GET /cashFlowDetailDay.json` supplies the existing 11 scalar accuracy metrics;
the public parent retains its established 12-field projection and `accuracy`
object. Existing metric zero-balance normalization remains specific to that
metric request.

Each parent also requires `GET /cashFlowDetail.json`, with fixed outer
`tntInstId` and serialized `bankAccountDetailCashFlowQueryVO`. Bind `valueDate`,
`accountNo`, `instId`, `tntInstId`, `currency`, `bankId` and `gmtCreate` to the raw
parent; `aliasName` is its selected native account alias and `forecastRecordId`
is its native `id`. The frontend constructs `gmtCreate` from the source property
before JSON serialization: absent values are omitted; explicit null remains
null. Never substitute capture time. Metric and occurrence requests have
separate bindings.

`cashflow_details` preserves the entire successful native `result.dataValue`
array, including source order, identical repeated occurrences, unknown nested
fields and paging-looking fields. Preserve Money components, amount strings,
native booleans and timestamps without unit conversion or matching calculations.
Provided contradictory context fails; absent identity echoes remain absent.

### Returned-set completeness

The frontend makes one contextual request, then limits display to 5000 rows.
That display limit is not an API page size. Native `count=0` and zero-valued
row paging metadata can accompany nonempty data and cannot prove totals,
pagination or source absence. Preserve native count as an observation, effective
reported total as unknown, and actual occurrences separately.

Until the exact endpoint's returned-set boundary has a qualified witness,
successful nonempty and empty occurrence arrays remain usable incomplete
results. Strict reads reject them; refresh cannot publish them. No invented
offset, terminal-empty probe or count derived from arrivals qualifies coverage.
Authentication, transport, business, binding and malformed-response failures
remain hard failures.

## Publication and evidence

The existing Custom query SDK owns allowlisting, authentication, physical
request/time budgets and failed-query traces. The leaf owns binding validation
and source coverage. Reserved `cashflow_curve`, `accuracy` and
`cashflow_details` namespace collisions fail instead of overwriting native data.

Live List never publishes. Only complete accepted nonempty refresh replaces a
compatible saved capture. Failed, incomplete and successful-empty refreshes
preserve the prior capture under host policy. Offline List replays the saved
composed scope without network access. Older base-only contracts require fresh
acquisition through existing incompatibility handling; no cache migration or
fabricated child data is supported.

Sequential sources do not promise a transactionally frozen backend snapshot.
Fake-CDP CLI checks prove local behavior. Production acceptance requires each
exact installed candidate's own native value/type/order and binding comparisons;
success of one leaf does not qualify the other.

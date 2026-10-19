# Collection VA rules

List uses one native JSON POST at pageNo1/pageSize1000 and validates the native
unique vaRuleId count against totalCount. The qualified width is not a measured
maximum. Only complete nonempty refresh publishes; failed/empty/incomplete refresh
preserves saved data. No implicit detail crawl occurs.

Get takes a native List `vaRuleId` and reads one independent native `resultObj`.
Required core business fields and exact identity echo are validated; explicit
nulls, unknown fields, precise values and optional warning settings stay native.
Backend refusals remain failures. Get does not publish or substitute List data.
`list --live --with-detail` composes only its selected window, atomically.

List `countries` and detail `creditAreas` remain distinct. `bankRuleId` refers to
another business object; bank-account VA-rule details remain unqueried.
ASCII-digit VA IDs display in numeric order with original-string tie-breaker,
then other IDs lexically; native identity strings and nested order stay unchanged.

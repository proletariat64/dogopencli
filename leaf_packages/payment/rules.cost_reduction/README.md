# Payment cost reduction

List only, one GET query to `/api/fundOut/costCutFlow/query` with pageNo0/pageSize1000.
Native success, exact integer page echoes, totalCount and unique `groupId`
identities determine completeness. totalPageNo0 is a placeholder. This qualified
width is not a measured maximum; incomplete responses never publish.

Filters use exact scalar strings or explicitly declared string-array members.
Same-field values OR, different fields AND. Commas and `*` are literal; blank
inputs reject and accepted values are unchanged. Return complete native rows,
sort root rows lexically by native identity, preserve nested order and precision.
Live never publishes; failed/empty/incomplete refresh preserves the saved capture.
This inquiry does not execute rules or prove realized savings or successful retries.

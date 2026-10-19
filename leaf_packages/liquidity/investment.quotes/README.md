# Investment quotes

Query one bounded QUOTED response with required `--from-date YYYYMMDD` and `--to-date YYYYMMDD`; equal bounds select one native value date. The native request uses `timeZone: null`, rowStart0 and qualified width5000. The accepted full-response contract makes one request without inferred offsets, fallback widths or fabricated totals. Native reported total stays null; observed rows, native identity quality and source coverage are reported separately. This is not unlimited upstream capacity.

`dogopencli liquidity list investment.quotes --live --require-complete --from-date 20260820 --to-date 20260820 --limit 0`

Full native records, unknown fields, order and JSON types are preserved; quote percentages and amounts are not reformatted. Strict incomplete/failed/complete-empty refresh preserves prior data. Ordinary List reads saved data; live acquisition does not publish. No runtime Duckdog import is added.

`dogopencli liquidity get investment.quotes QUOTATION_ID` sends quotationOrderId and returns the entire native baseResult.data root, including sibling product, approval, negotiation, log and win sections. Identity is the native nested quotationDetail.quotationId; it is validated before projection without flattening or an invented root ID.

Add `--live --with-detail --limit 1` to List to fetch only its selected window as `{record, detail}` pairs. The same-value binding uses native List quotationOrderId. Any detail failure fails the whole query; successful details cannot repair incomplete List identity quality. Direct Get and composition preserve saved List data and fetch no separate history/children.

# Investment strategy benchmarks

`dogopencli liquidity list investment.benchmarks` reads investment benchmark rule
configuration. This package supports list only and exposes no business filters.
The host provides refresh, offline list, prune, describe and help.

The fixed historical reference is release `v0.4.3`, resolved commit
`a7e5c5ead675487646eb9a53d73ec9e0aeb944f9`,
[`INVESTMENT_BENCHMARKS`](https://github.com/proletariat64/dogopencli/blob/a7e5c5ead675487646eb9a53d73ec9e0aeb944f9/src/dogopencli/plugins/liquidity/leaves.py#L880).
Historical code is reference evidence only; this package imports neutral host
utilities and contains no historical runtime.

| Contract | Native behavior |
| --- | --- |
| Entry | `https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt` |
| Inquiry | POST JSON `/queryStrategyBenchmarkRuleList.json` |
| Fixed body | `tntInstId="GUAPW3SG"`, `timeZone="GMT+08"`, `valueDateStart=""`, `valueDateEnd=""` |
| Pagination | Zero-based `rowStart` offset; `pageSize=5000` |
| Envelope | Boolean `success`; records at `data.data`; fixed total at `data.totalCount` |
| Identity | Native `id`, retained with its JSON type; no generated identity |

The package preserves complete native objects, including unknown fields, exact
JSON decimals, null, empty string, zero and timestamps. `valueType` determines
how a native benchmark `value` should be interpreted; the package performs no
unit, rate, currency or timezone conversion. These configured rules are not
realized investment returns.

Collection checks fixed totals, page capacity, progress and native identities.
Identical duplicate identities yield incomplete evidence; conflicting duplicate
content fails. Strict acquisition refuses incomplete results. Live does not
publish cache; a qualified nonempty refresh replaces this leaf's temporary cache.
Empty or failed refresh preserves the previous snapshot. Offline list performs no
business request. Refresh does not import records into Duckdog.

Automated evidence is in `tests/integration/test_investment_benchmarks.py` and uses
installed directory/ZIP packages, the public CLI and controlled CDP responses.
The tests prove request/parsing and host lifecycle behavior, not production
availability. Local and cn.ant nonempty production comparison, Duckdog import and
final data cleanup/uninstall remain separate acceptance gates under spec #257.

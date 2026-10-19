# operations.account_strategies

List the native default account-operation strategy view:

```bash
dogopencli liquidity list operations.account_strategies -h --format text
dogopencli liquidity list operations.account_strategies --live --limit 0 --require-complete
dogopencli liquidity refresh operations.account_strategies --currency USD --require-complete
dogopencli liquidity list operations.account_strategies --currency USD
```

POST JSON `/strategyManage/queryList.json` on `iliquidity.alipay.com` uses native
zero-based `rowStart` and qualified `pageSize=5000`. No tenant, date, status or
default approval filter is sent. Standard SDK fixed-total, identity and page-gap
checks establish coverage; no separate terminal-empty request is made or claimed.
The width is qualified, not a maximum-capacity claim. Optional native page echoes
are checked for valid type/stride, not an unavailable per-request offset binding.

Identity is native `(aliasName,currency,version)` with integer version. All returned
versions, Invalid records, unknown fields, nulls, precision and native arrival
order remain unchanged. This default view does not establish all history or latest
approval state. Configuration `status` differs from approval `processStatus`.

`--entity`, `--bank`, `--alias`, `--currency`, `--account-type`, and
`--operation-strategy` pass native string arrays: repeated values OR, dimensions
AND. `--cover-algorithm` passes one Y/N value. Values must be nonblank. Strategy
codes match known complete display-label members; both Self-Build Cash Pool and
Self-Built Cash Pool are supported without changing native text or duplicates.

Bare offline List replays its saved scope. Explicit filters can narrow the local
view but cannot prove coverage outside that native scope; strict reads reject
unproved coverage. Saved scope treats filter arrays as sorted, deduplicated sets.
No Get, related account acquisition, algorithm execution or time conversion occurs.

# Transfer rules

Read native configuration records through the host List SDK.

```bash
dogopencli liquidity list rules.transfer --live --limit 0
dogopencli liquidity refresh rules.transfer --require-complete
dogopencli liquidity list rules.transfer
```

A single GET `/transferRuleQuery.json` sends fixed tenant GUAPW3SG and a serialized query with empty debit/credit entity arrays, rowStart=0 and pageSize=5000. Records are `result.transferRuleVOS`, total is `result.ruleCount`, identity is native `ruleId`. All nested native conditions and unknown fields are preserved without projection.

The width is supported by historical successful requests, not a measured backend maximum. The SDK owns deadlines, retries, completeness and cache publication. A short final page is valid; duplicate identities, count shortfall and interior page gaps are incomplete. Conflicts keep the last arrival while remaining incomplete. `--require-complete` rejects incomplete acquisitions and leaves the prior cache intact.

## Native detail

`dogopencli liquidity get rules.transfer RECORD_ID` queries `/queryTransferRuleDetail.json` using native `ruleId` and validates root `ruleId`. The lookup is the same value as native List `ruleId`; the original fields, nested arrays, JSON types and exact values are retained. Separate history, logs and child endpoints are unqueried. Get never publishes cache or Duckdog data.

`dogopencli liquidity list rules.transfer --live --with-detail --limit 1` returns selected `{record, detail}` pairs, preserves List order/quality and the saved List, and fails the entire query on any Detail failure.

# investment.strategies

Get-only strategy settings inquiry through the host Get SDK:

```bash
dogopencli liquidity get investment.strategies -h --format text
dogopencli liquidity get investment.strategies RULE_CODE
```

Use a verified native `strategyRuleCode`, distinct from `strategyRuleId` and
`mainStrategyTemplateId`. The leaf sends only that code in a form POST to
`/queryIncrementStrategyRuleDetail.json` and requires its exact native root echo.
It preserves the complete root, nested arrays, unknown fields and native values.

The result covers this native settings response. Separate histories and strategy
execution results are unqueried. Get is live-only and creates no List cache or
Duckdog dataset.

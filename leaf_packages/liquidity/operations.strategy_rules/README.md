# Strategy rule records

This independent List reads native main and sub strategy rule records from
`/queryStrategyRulePage.json`. Each acquisition selects one native category.

```bash
dogopencli liquidity list operations.strategy_rules --category MAIN_DECISION_STRATEGY --live --limit 0 --require-complete
dogopencli liquidity list operations.strategy_rules --category SUB_STRATEGY --strategy-type PRINCIPAL_PLANNING --live --limit 0 --require-complete
dogopencli liquidity refresh operations.strategy_rules --category SUB_STRATEGY --require-complete
dogopencli liquidity list operations.strategy_rules --limit 0
```

For `SUB_STRATEGY`, repeat `--strategy-type` to select native types. Omitting it
selects the UI's three types: `PRINCIPAL_PLANNING`, `INVESTMENT_PORTFOLIO` and
`INVESTMENT_PREFERENCE`. A type is invalid with `MAIN_DECISION_STRATEGY`.
The native request contains no tenant field.

The native main List currently returns `strategyCategory: "SUB_STRATEGY"` with
an empty `strategyType`, despite the explicit `MAIN_DECISION_STRATEGY` request.
Complete cross-width acquisitions establish separate main/sub scopes; the
returned field is preserved unchanged. This qualified main echo is accepted
only with the empty native type; a main response carrying a selected sub type
is rejected. Interpret capture scope from the request, not that source label.

`id` identifies the physical source record. `strategyRuleId` and `version`
retain their separate meanings; records sharing a logical rule ID are not merged.
All source fields, timestamps, statuses, nested values and unknown fields remain
unchanged. `strategyRuleContent` remains a native string when returned as a string.
Referenced sub-strategy IDs are not resolved, and independent history/detail and
all operating actions are excluded.

The host List SDK collects offset pages and verifies native totals and physical
identities. Live inquiry does not publish saved data. Complete nonempty refresh
may replace the retained capture; successful empty, failed or incomplete refresh
preserves the previous capture. Offline List replays the retained scope and
capture time. The cache is a retained query capture, not a historical dataset.

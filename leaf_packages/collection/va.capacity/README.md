# VA capacity

`collection.va.capacity` exposes inquiry-only VA-rule usage and capacity rows.
Install the package explicitly. It uses the host List SDK's qualified short-page
termination with page numbers starting at 1 and pageSize 100. The backend's
pagination total is unreliable and does not control acquisition or completeness.

```bash
dogopencli plugins install /path/to/collection.va.capacity.zip
dogopencli collection list va.capacity --live --require-complete --limit 0
dogopencli collection refresh va.capacity --require-complete
dogopencli collection list va.capacity --va-rule-id RULE_ID --limit 0
```

`--bank-va-rule-id` matches `bankAccountVaId`; `--va-rule-id` matches `ruleId`.
Both are repeatable exact local filters: OR within a flag, AND between flags.
They do not narrow the native acquisition. All native fields and values remain
unchanged; the output uses stable native-rule identity ordering.

Completion follows the independently qualified first-short-page contract,
including a zero-row page after an exact multiple of 100. The SDK retains
deduplication/conflict evidence, bounded execution and strict publication rules.
`reported_total` stays null; row capacity counters named `totalCount` remain
untouched. This does not infer warning classification, expand VA-rule details,
or query individual virtual accounts. Failed/empty/incomplete refresh preserves
the prior snapshot; live never publishes.

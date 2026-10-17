# B02 explicit Duckdog import

Issue #259 delivers six independent settings inquiry packages. The existing
ignored helper at `.agents/skills/duckdog-import/scripts/import_settings.py`
receives a bounded extension through
[`migration-b02-duckdog-import.patch`](../../scripts/patches/migration-b02-duckdog-import.patch).
Apply the B01 compatibility patch first, then B02, from the repository root:

```bash
patch --batch -p1 -i scripts/patches/migration-b01-duckdog-import.patch
patch --batch -p1 -i scripts/patches/migration-b02-duckdog-import.patch
```

Do not reapply a patch to an already patched helper. B02 retains the established
complete live acquisition policy and storage mechanism. Its selector allowlist is:

- `liquidity/rules/action_mapping`
- `liquidity/rules/funding`
- `liquidity/rules/fx_settlement`
- `liquidity/rules/operation`
- `liquidity/rules/realtime`
- `liquidity/risk/thresholds`

Each manifest declares its own relation:

| Leaf | Relation |
| --- | --- |
| `rules.action_mapping` | `liquidity_rules_action_mapping` |
| `rules.funding` | `liquidity_rules_funding` |
| `rules.fx_settlement` | `liquidity_rules_fx_settlement` |
| `rules.operation` | `liquidity_rules_operation` |
| `rules.realtime` | `liquidity_rules_realtime` |
| `risk.thresholds` | `liquidity_risk_thresholds` |

The current action-first acquisition command is
`dogopencli liquidity list <dotted-leaf> --live --limit 0 --require-complete --format json`.
The two historical hyphenated selector spellings become the current underscore
spellings; no aliases are added. All six have an empty host scope and require
unfiltered live list metadata. Cached output, native get output, local selectors,
truncation, inconsistent counts and incomplete acquisition are rejected.

Refresh and adapters never import. Run the helper explicitly, either to acquire
live JSON or with a provenance-qualified private `--input` file. Production use
requires separately verified package UAT and inquiry-only authenticated transport.
The public CLI tests use synthetic CDP responses and temporary stores, compare
full records in DuckDB and Parquet, verify exact acquisition metadata and command,
and verify rejected replacements preserve the imported rows.

Actual helper hashes for this extension:

- Before B02: `2311816210640eebb19821f383ff353d963fbde953e28ec887c774eed0c04c75`
- After B02: `39769eba54ed5efcb2015e791c3d1dd14321d165bc38dd907ca77c84da6ab81f`

The sanitized tracked fixture includes unrelated historical sections absent from
the active helper. Tests apply B01 and B02 patches to that fixture independently;
these hashes identify the actual ignored helper edited for this ticket.

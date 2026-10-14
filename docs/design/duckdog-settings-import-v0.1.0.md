# Duckdog settings and reference import contracts

Storage and publication authority: [Duckdog specification #160](https://github.com/proletariat64/dogopencli/issues/160).

Declared on 2026-10-14 for the user-authorized Liquidity settings audit.
Use the storage and publication policy in [duckdog v0.1.0](duckdog-v0.1.0.md).
These declarations extend importer support; they do not establish leaf activity.

The public `dogopencli describe liquidity <group> <leaf> list` declares the native
list identities below. The importer validates each identity component, tuple
uniqueness, complete live acquisition, unfiltered query and matching counts before
publication. It preserves full JSON, including nested configuration and unknown
fields, in Parquet. Views expose identity columns as strings plus `_record`.
Settings and reference directories share current-only replacement storage; registry
`kind=settings` denotes this storage policy. The acquisition metadata retains the
source leaf's actual kind. There is no runtime/history import in this helper.

Selectors start with `liquidity/`; views replace slashes with underscores.

| Selector suffix | Native list identity |
| --- | --- |
| cash/accounts | aliasName, currency |
| cash/pools | id |
| cash/credit-lines | id |
| investment/products | incrementProductId |
| investment/benchmarks | id |
| risk/thresholds | benchmarkId |
| risk/sla | slaConfigId |
| rules/funding | id |
| rules/operation | ruleId |
| rules/realtime | id |
| rules/action-mapping | id |
| rules/fx-settlement | id |
| rules/forecast | ruleId |
| rules/waterlevel | bufferId |
| rules/transfer | ruleId |
| network/realtime | id |
| network/bank-baselines | aliasName |
| network/account-capabilities | id |
| reference/banks | bankId |
| reference/entities | id; additionally unique string instId |

All acquisitions use `list --live --limit 0 --offset 0 --require-complete --format json`
without optional filters. Expected `.meta.query` and `.meta.scope` are empty.
Extra filters are rejected. Calendars, ledger/accounts and business-lines
remain excluded because the user has already selected them for retirement.

Activity is assessed separately: a modification within approximately two years
keeps a leaf; older than one year is annotated for manual review. Empty results or
missing/unparseable dates need confirmation. Recent nested configuration changes
also establish activity. Old timestamps establish age, not proof that a backend
job stopped. Previously confirmed model retirement retains its independent basis.

## B01 pricing retirement

The business-confirmed retirement in #164 and specification #172 removes pricing
factors and strategies from active import contracts. All six retired pricing
selectors refuse live acquisition and saved-input publication. Existing datasets
and historical analysis remain intact; no import, replacement, or cleanup is
authorized by retirement. R01-only selectors retain their separate scope.

## R01 retirement

R01 #167 and specification #175 retire cash/groups, investment/strategies,
rules/notification and ledger/customers from active import contracts. Both live
acquisition and saved-input publication, including direct publication, refuse
before opening input or storage. Historical selectors and datasets remain readable
for analysis. Calendars, ledger/accounts and business-lines remain excluded.

The former cash/groups declaration used identity `id` and default query/scope
`{"equiCurrency":"USD"}`. The former investment/strategies identity was
`strategyRuleCode`, rules/notification was `id`, and ledger/customers was
`customerNo, version`. These are historical evidence, not active import contracts.

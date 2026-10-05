# Liquidity Batch F: four bounded inquiry lists

Observed: 2026-10-05
Scope: general
Status: snapshot

Implementation scope: issues #109–#112 on the shared Batch F branch.
Implementation and independent production CLI UAT are pending.

The authoritative specifications are [#109](https://github.com/proletariat64/dogopencli/issues/109),
[#110](https://github.com/proletariat64/dogopencli/issues/110),
[#111](https://github.com/proletariat64/dogopencli/issues/111), and
[#112](https://github.com/proletariat64/dogopencli/issues/112).
The user requested one PR for all four tickets. The starting baseline is
`495e90005f41183b0a7e9561b835545d3207b51c` (`master`, v0.2.8).

| CLI list | Accepted inquiry scope | Capture profile | Completion proof |
| --- | --- | --- | --- |
| `risk sla list` | Native default SLA configuration scope; one fixed 5000-row request | settings snapshot | Raw arrivals = unique `slaConfigId` = native total |
| `forecast accuracy list` | One explicit account and record creation query date; at most 100 base records | runtimes history | Complete base coverage and all native metric compositions |
| `risk account-capacity list` | Explicit sorted set of 1–10 distinct account aliases | runtimes history | Exactly one validated native object for each requested alias; no native global total |
| `investment rfqs list` | TARGET_RFQ with paired explicit dates; one fixed 5000-row request | runtimes history | Raw arrivals = unique `inquirySubTaskId` = native total |

All lists use the shared inquiry transport and independent projection schemas
and cache scopes. Default reads are offline; explicit refresh publishes
atomically; live reads never publish or fall back. Source times remain distinct
from capture time; unproven source timezones remain unknown. Existing detail
caches are independent, and no list refresh initiates a detail crawl.

Rules monitoring remains HOLD. FULL_RANGE_RFQ, full-account accuracy,
cross-date accuracy, account discovery, and the other seven Batch F candidates
remain outside this delivery. This PR does not bump, merge, or release.

## Verification record

Focused fake-CDP public CLI checks, repository Ruff/format/doc gates,
Standards/Spec review, local Kimi review, and per-leaf production CLI UAT
will be recorded independently before delivery. Native observations in the
specifications establish implementation contracts; they do not establish UAT
of the new public CLI.

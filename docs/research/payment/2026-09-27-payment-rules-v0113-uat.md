# Published v0.1.13 payment rules UAT

Observed: 2026-09-27
Scope: payment
Status: snapshot

## Artifact and execution

Downloaded the wheel and SHA256SUMS from the published GitHub release v0.1.13.
Verified wheel SHA256:
`356f432618eb1f86c33e3b36ae884f2e68c9b1aeaaeec4baf1c332425b79e6a6`.
Installed into an isolated environment and asserted both distribution and runtime
version 0.1.13 and imports from that environment, with PYTHONPATH unset.
Release commit: `35ba9f7` on master.

Ran the public CLI through its installed entry-point function against the existing
authenticated dedicated Chrome on CDP 9222, under normal inquiry coordination.
The acceptance harness reused the [implementation UAT matrix](2026-09-27-payment-rules-implementation-uat.md).
A new private configuration and SQLite cache were created under ignored tmp/.
Only aggregate counts and assertion results were logged; raw records and real
filter values were not printed or committed.

## Results

All 424 assertions passed against the published artifact:

| Capability | Complete records | Assertions |
| --- | ---: | ---: |
| same-bank-transfer | 34 | 56 |
| cost-reduction | 30 | 122 |
| retry | 89 | 155 |
| bank-switch | 46 | 90 |

The final assertion verifies the operator cache again. SHA256 values of the
operator database, WAL and SHM remained unchanged after each capability and
at the end. Every live query also preserved the private published cache.

Covered cold cache, atomic refresh, full cached/live agreement, all 26 domain
flags (positive, nonmatch, repeated OR, whitespace rejection), each positive
filter live, and bank-switch's combined five-field query. Also covered defaults,
last/beyond windows, all, projection, JSON/table, invalid options/conflicts,
freshness/completeness flags, help aliases and JSON/text describe. Cached and
help/describe checks used an unreachable CDP endpoint to verify offline behavior.

## Evidence limits

This run covers the four released payment-rule capabilities, not every existing
payment/collection command. No login/logout, browser restart, production mutation,
PTR action or flow-detail revalidation was performed. The separate logout-scope
and secure-launcher login-to-payment-cost UAT dependencies remain open; #54's
flow identity blocker is unchanged. Production overflow, malformed envelopes,
stale/corrupt caches and adversarial cross-child matches remain covered by the
previous synthetic SIT evidence, not newly claimed production observations.

# Factor type definitions CLI production UAT

Observed: 2026-10-05
Scope: general
Status: snapshot

Root agent executed the independent public CLI production inquiry on the
user-authorized Chrome CDP port 9223, against the fixed Liquidity tenant.
No source identifiers, labels, tenant business instances or raw responses are
recorded here. Counts describe this observation, not a frozen enumeration.

- GET `/getPriceEnv.json` executed once per invocation, with fixed tenant-only
  query, no rowStart/pageSize or fallback endpoint.
- Ten native definitions had ten unique codes. All 30 code/description/englishName
  scalar fields aligned between native data and the CLI projection.
- Metadata reported `kind=reference`, `complete=true`, `reported_total=null`.
- Explicit refresh followed by disconnected offline list reused the same capture
  and fetched_at (`2026-10-05T10:31:01.866566+00:00`), with no browser access.
- Live inquiry left the real SQLite database byte hashes unchanged.

The first authentication readiness attempt timed out. After a fresh healthy
and authenticated browser check, a bounded retry passed the complete UAT.
Authentication failure was not represented as empty data.

Public CLI fake-CDP/real-SQLite acceptance additionally covers malformed identity,
wrong/missing success and containers, business/auth/permission/HTTP failures,
future codes and unknown labels, raw excluded-field identity conflicts,
identical arrivals as incomplete, strict rollback, safe partial publication,
complete empty replacement, legacy schema separation and independent factor-values
captures. These negative/empty checks do not claim corresponding production scopes.

Existing factor-values native production smoke is coordinated separately by the
root agent. Rules monitoring remains HOLD; factors get and broader pricing
calculations are outside this delivery. Review and release status remain separate
from the passing new-list production UAT.

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
  and fetched_at (`2026-10-05T10:33:20.309583+00:00`), with no browser access.
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

Existing factor-values native production smoke also passed: the verified
20261004 single-day scope was explicitly refreshed and read through its public CLI.
A subsequent factor-definitions refresh preserved the same factor-values capture
and its runtimes kind. This checks the existing value contract and cache isolation
without claiming broader factor-values date coverage. Rules monitoring remains HOLD; factors get and broader pricing
calculations are outside this delivery. Standards/Spec review and release status remain separate
from the passing new-list production UAT. User authorization for local Kimi/API source-spec transfer was granted on 2026-10-05. The actual static Standards/Spec review of [source commit `fe33524`](https://github.com/proletariat64/dogopencli/commit/fe335248961838db52a0a263f10eff61abe7de1c) completed successfully with no confirmed correctness/spec defects; confidence: 4/5. Tests, lint, graph analysis and production UAT were run independently by the root coordinator, not by Kimi. This subsequent documentation-only commit is not claimed to have been re-reviewed by Kimi.

The earlier automatic approval rejection is historical: the user subsequently
authorized the source/spec transfer, enabling this completed review. The initial ten-minute review attempt timed out; a five-minute continuation
completed with exit code 0 and produced the final review.

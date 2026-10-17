# Migration B01 acceptance evidence

Observed: 2026-10-17. Specification:
[#257](https://github.com/proletariat64/dogopencli/issues/257), parent
[#218](https://github.com/proletariat64/dogopencli/issues/218).

## Delivery boundary

Three independent list packages are maintained under root `leaf_packages/`,
outside the four bundled pilot identities. Each owns its endpoint, native parser,
identity and manifest. Host imports are neutral contracts and collection helpers;
no retired business runtime is restored. Banks country selection is local in live
and cached modes. Refresh keeps the full native acquisition. Native-only scope
parameters are excluded from live post-filters; cached coverage compares native
scope before permitting a local-filter change.

User corrections supersede the original ticket's historical delivery clauses:
cn.ant is only an HTTP ZIP/SHA256 server. All business execution is local. Delivered
leaves remain installed in the host environment on merged master; task-generated
business data/cache are cleared, while host configuration and authenticated SSO
are preserved. Automatic merge requires all checks, UAT, CI and exact OCR zero.
No formal release is part of this batch.

## Per-leaf production evidence

The authenticated task profile used allowed CDP port 58353. Human SSO completed,
then login verified headless authentication. Raw responses and comparison records
remain private and are excluded from Git, OCR and public evidence.

| Leaf | UTC live capture | Native rows | Page size / identity | Result |
| --- | --- | --- | --- | --- |
| reference.banks | 2026-10-17 15:07:48 | 930 | 5000 / bankId | complete |
| investment.benchmarks | 2026-10-17 15:08:08 | 50 | 5000 / id | complete |
| rules.forecast | 2026-10-17 15:08:26 | 4 | 10 / ruleId | complete |

These are observed counts, not fixed acceptance targets. Forecast retained the
native fixed `instId=["Z21"]`; benchmarks retained empty native date bounds.
Each HTTP-installed ZIP passed live without publication, nonempty refresh, and
exact offline record readback. Offline also passed with CDP explicitly unavailable.
Banks repeated exact country selection matched 24 saved/native rows in both live
and offline modes, without adding native request fields.

Each genuine complete live envelope was explicitly imported through the existing
Duckdog settings importer, with the reviewed B01 metadata-compatibility patch.
DuckDB views and Parquet were read back in row order. Full native records, JSON
types, amount values, identity multiplicities and original acquisition metadata
matched the source for all 930 / 50 / 4 records. Refresh itself did not import data.
The tracked patch supports only the three approved current leaf identities and
rejects cached, filtered, incomplete, contradictory or truncated input.

## Isolated historical comparison

The fixed GitHub release `v0.4.3` resolves annotated tag
`4b315c2ad13c8cc9bd4c89f28ee717b3789bc129` to commit
`a7e5c5ead675487646eb9a53d73ec9e0aeb944f9`. Its archive and modules stayed
outside the repository/new runtime. A separate historical process had sockets
blocked and replayed the same privately captured native response bytes. Native
method/path/request scope, pagination width, full record fields, JSON types,
amounts, identity fields and reported counts matched the new installed CLI for
each leaf. JSON-encoded VO whitespace was normalized before request comparison;
no business field was normalized. No unexplained difference remained.

## Initialization and final state

The authorized one-time historical initialization cleared 1321 recognized query
cache files and business records in the daily host and historical dataset
DuckDBs. It removed 50 old Parquet/raw-envelope files. Twenty-two intentionally
invalid or unknown-schema test fixture databases were preserved; none was treated
as a qualified query cache. The first pass stopped safely on an invalid SQLite
fixture, then the idempotent pass completed recognized schemas. Installed pilot
leaves, ownership records, configuration and all authentication profiles survived.
Later batches must preserve newly generated evidence instead of repeating this
historical reset.

Final installed-state and business-data cleanup verification is completed after
merge into master. The task's authenticated profile must remain available.

## Artifact transport and verification

Three ZIPs plus SHA256SUMS are hosted in the task-owned cn.ant HTTP directory.
Public access to the new port returned HTTP 502, so acceptance used an SSH local
forward to that same remote HTTP service. All ZIPs were genuinely downloaded over
HTTP, hash-checked, and installed by the public HTTP installer. No dogopencli,
Chrome or Duckdog ran on cn.ant; no production data was uploaded there.

Final artifact hashes, source-independent execution, full checks and review
results are recorded in the completion update on #257. Installation alone and
synthetic tests are not presented as production evidence.

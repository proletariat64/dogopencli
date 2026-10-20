# Cash accounts

B19 / #278 provides one `liquidity.cash.accounts` List. It collects the cash
directory, the full account baseline list, and one native detail for every
baseline alias. Baseline List/Get remain internal sources. No public Get or
additional leaf is registered.

`execution: custom` expresses the dependent queries. The host still controls
the allowlisted transport, authentication, pagination, retries, request/time
budgets and cache publication. The adapter never opens a browser or writes cache.

| Source | Inquiry | Coverage |
| --- | --- | --- |
| Cash | `/queryintnalbkactlist.json` | Qualified short-page/hole SDK; fixed wallet=false; native count ignored |
| Baseline | `/bankAccountBaseLineQuery.json` | Independent fixed-total offset acquisition, pageSize=1000 |
| Detail | `/bankAccountBaseLineDetail.json` | One aliasName lookup per baseline row; validate returned identity/context |

Output contains one row per `(aliasName, currency)`, in cash order followed by
baseline-only rows. Baseline aliases must be unique. Overlapping sources must
agree on alias/currency and any nonempty bankId/instId context. Each row retains
the native objects under `source_metadata.raw.cash`, `.baseline` and `.detail`.
Unknown fields, nested values and decimal precision remain unchanged.

Baseline owns `accountType` and `status`; cash owns `gmtModified` and `operator`.
Other fields prefer baseline, then cash, then detail. Provenance and conflicting
source values remain visible in `source_metadata`. Detail coverage is explicitly
`succeeded`, `refused` or `missing`.

Only an outer-success response with inner `success=false` qualifies as an
individual detail refusal. Authentication, transport, malformed responses and
identity disagreement abort the operation. Qualified refusals and unmatched
source rows produce usable incomplete live output. Strict queries reject them;
refresh preserves the prior complete cache. Local currency, bank, status,
account number and alias filters run after full acquisition.

The assembled directory has no fabricated backend total. Independent source
evidence, list matching, detail coverage and field inventory are retained under
`meta.acquisition.attempts`, including on offline replay. Cash pagination holes
remain SDK evidence; this package contains no legacy hole/effective-total logic.

The fixed v0.4.3 source at `a7e5c5ead675487646eb9a53d73ec9e0aeb944f9`
is business-output comparison material only. The package imports no legacy
runtime. Fake-CDP checks establish implementation behavior; current full
baseline/detail production qualification and exact-candidate acceptance remain
separate requirements.

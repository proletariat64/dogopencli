# Liquidity whitelist and blacklist inquiries

Authority: [specification #176](https://github.com/proletariat64/dogopencli/issues/176), [delivery tracker #168](https://github.com/proletariat64/dogopencli/issues/168), ADR 0019 and ADR 0020. On 2026-10-15 the user confirmed bank identity as bankId with the greatest native gmtCreate selected. All three lists are executable in this source revision; production acceptance, merge and release remain distinct gates.

## Commands and identity

| Command | Availability | Native row identity | Kind |
| --- | --- | --- | --- |
| `liquidity reference whitelist entity list` | Executable | Nonempty string `instId` | settings |
| `liquidity reference blacklist account list` | Executable | Nonempty string `aliasName` | settings |
| `liquidity reference blacklist bank list` | Executable | bankId; select greatest gmtCreate | settings |

These settings sources are separate from the entity directory, bank directory and composite cash-account list. They use independent named HTTP GET inquiries; no detail, Edit, arbitrary endpoint or JavaScript command is exposed. A list's `id` field is not automatically its native identity. Production observations showed repeated placeholder integer IDs on the entity and account responses. The verified identities above are native object selectors and were checked across the complete same-run records and overlapping pages.

The bank response contained repeated bankId values with differing creation times. The user-approved business projection selects one complete row per bankId, using the greatest gmtCreate before local filters. It does not claim a native row/version identity or concatenate timestamps into IDs. gmtCreate must be a nonnegative integer epoch-millisecond value; missing, null, boolean, string and negative values fail. All equal-time conflicting content fails, including older ties hidden by a later row. Identical ties collapse. The first observed order of banks remains stable; gmtModified never decides the winner.

Bank reported_total and arrivals retain native row counts; collected_total, unique_count and returned rows refer to selected banks. Additional rows are recorded in duplicate_count and BANK_LATEST_CREATED_SELECTED warns without labelling differing timestamps identical. The bank_row_occurrences_latest_gmtCreate evidence contains raw and selected counts plus the named bank-blacklist-latest-gmtCreate-v1 selection contract. Raw page overlap and terminal witnesses remain mandatory for complete; selecting fewer banks is not a count shortfall when every native row is covered. Incomplete raw acquisition remains incomplete and strict queries reject it. Cached evidence validates the distinction and replays without querying or reselecting source history.

## Acquisition and filters

Each executable source requires boolean `resultFlag=true` and nested `result.success=true`, an array of objects at `result.data`, and equal nonnegative integer counts at `count` and `result.count`. Missing or malformed success markers, mismatched totals, invalid native identities, nonempty foreign tenant values and conflicting content fail without business data.
The observed account DTO carries an empty tenant field; that value stays empty.
Scope is bound by the fixed native request, rather than synthesizing a row echo.

The production request carries the fixed tenant, timezone and source variant in a named JSON query object. The verified `rowStart` unit is a zero-based row offset. Acquisition prefers `pageSize=5000`; observed silent truncation restarts a clean candidate at verified `pageSize=1000`. A failed authentication, transport, business query or parse is not a page-size rejection and never triggers fallback. No explicit backend size-rejection diagnostic was proven, so such refusals remain errors.

The collector checks stable totals, native identities and content, overlapping pagination boundaries, and a terminal empty response at the reported boundary. Per-row pagination fields observed as zero defaults are not treated as server pagination echoes. Actual arrivals determine offset advancement under a cap. Page and time budgets remain finite, and output `--limit`/`--offset` never change native acquisition. Usable incomplete candidates retain their counts and pagination evidence and warn with `complete=false`; `--require-complete` withholds incomplete data and publication.

All supported filters are exact local matches after acquisition. They do not change the native request or prove a narrower backend scope.

| List | Local flags and native fields |
| --- | --- |
| Entity whitelist | `--entity` / `instId`; `--financial-code` / `instCode`; `--status` / `status` |
| Account blacklist | `--entity` / `instId`; `--bank-id` / `bankId`; `--account-alias` / `aliasName`; `--status` / `status` |
| Bank blacklist | `--bank-id` / `bankId`; `--status` / selected row's `status` |

Default output retains all statuses, including VALID and INVALID. Status values do not establish whether a configuration is active. Unsupported filters are rejected before browser work. JSON preserves native types, nulls, empty strings, zero values, nested structures and source timestamps. Capture time is separate from modification time.

## Temporary slots and output

```bash
dogopencli liquidity reference whitelist entity list --live --limit 0 --require-complete
dogopencli liquidity reference blacklist account list --live --limit 0 --require-complete

dogopencli refresh liquidity reference whitelist entity --require-complete
dogopencli refresh liquidity reference blacklist account --require-complete

dogopencli liquidity reference whitelist entity list --limit 0
dogopencli liquidity reference blacklist account list --limit 0
```

Each executable leaf owns one temporary SQLite slot. Explicit nonempty refresh atomically replaces only that slot. Empty refresh, hard failure and strict incomplete rejection preserve its prior contents. Live never publishes; default offline replay opens neither Chrome nor duckdog. Each executable leaf's prune removes only its own slot and does not create an absent database. JSON, table, fields, describe and snapshot inventory use the existing public behavior and quality metadata. There is no external dataset or importer integration.

## Production proof and remaining gate

Native verification used a new dedicated profile and permitted loopback CDP port in the 91xx range, with human SSO and automatic headless handoff. Both page sizes were tested independently. A complete 1000-row pagination run matched the 5000-row response for entity and account sources; small offset-one and offset-ten windows matched the corresponding slices. Both sources retained VALID and INVALID rows. These are dated observations, not permanent totals or guarantees that future scopes cannot change.

Raw evidence, native identifiers, internal page URLs and authentication material remain private. Public CLI production UAT, local synthetic tests and independent code review must be reported separately. The original two-leaf delivery was PR #186; its bank identity gate is superseded by the user's explicit selection rule, not retroactively marked passed. Independent bank execution/lifecycle UAT is required before claiming three-leaf acceptance or closing #168/#176. No release is implied.

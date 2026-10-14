# Liquidity whitelist and blacklist inquiries

Authority: [specification #176](https://github.com/proletariat64/dogopencli/issues/176), [delivery tracker #168](https://github.com/proletariat64/dogopencli/issues/168), ADR 0019 and ADR 0020. This source change enables two lists and keeps the third explicitly unavailable. It does not complete acceptance of the three-list requirement or publish a release.

## Commands and identity

| Command | Availability | Native row identity | Kind |
| --- | --- | --- | --- |
| `liquidity reference whitelist entity list` | Executable | Nonempty string `instId` | settings |
| `liquidity reference blacklist account list` | Executable | Nonempty string `aliasName` | settings |
| `liquidity reference blacklist bank list` | Unavailable: native row/version identity remains unproven | Unresolved | settings |

These settings sources are separate from the entity directory, bank directory and composite cash-account list. They use independent named HTTP GET inquiries; no detail, Edit, arbitrary endpoint or JavaScript command is exposed. A list's `id` field is not automatically its native identity. Production observations showed repeated placeholder integer IDs on the entity and account responses. The verified identities above are native object selectors and were checked across the complete same-run records and overlapping pages.

The bank response contained duplicate `bankId` values with differing creation times. A creation timestamp does not establish a version identity. The bank path remains discoverable through help, describe and snapshot inventory, but refuses execution without opening Chrome or changing cache. It has no executable refresh or prune. Enabling it requires a native identity/version contract and independent production acceptance; concatenating a display code with a timestamp is not sufficient proof.

## Acquisition and filters

Each executable source requires boolean `resultFlag=true` and nested `result.success=true`, an array of objects at `result.data`, and equal nonnegative integer counts at `count` and `result.count`. Missing or malformed success markers, mismatched totals, invalid native identities, tenant mismatches and conflicting content fail without business data.

The production request carries the fixed tenant, timezone and source variant in a named JSON query object. The verified `rowStart` unit is a zero-based row offset. Acquisition prefers `pageSize=5000`; observed silent truncation restarts a clean candidate at verified `pageSize=1000`. A failed authentication, transport, business query or parse is not a page-size rejection and never triggers fallback. No explicit backend size-rejection diagnostic was proven, so such refusals remain errors.

The collector checks stable totals, native identities and content, overlapping pagination boundaries, and a terminal empty response at the reported boundary. Per-row pagination fields observed as zero defaults are not treated as server pagination echoes. Actual arrivals determine offset advancement under a cap. Page and time budgets remain finite, and output `--limit`/`--offset` never change native acquisition. Usable incomplete candidates retain their counts and pagination evidence and warn with `complete=false`; `--require-complete` withholds incomplete data and publication.

All supported filters are exact local matches after acquisition. They do not change the native request or prove a narrower backend scope.

| List | Local flags and native fields |
| --- | --- |
| Entity whitelist | `--entity` / `instId`; `--financial-code` / `instCode`; `--status` / `status` |
| Account blacklist | `--entity` / `instId`; `--bank-id` / `bankId`; `--alias-name` / `aliasName`; `--status` / `status` |

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

Raw evidence, native identifiers, internal page URLs and authentication material remain private. Public CLI production UAT, local synthetic tests and independent code review must be reported separately. Tracker #168 stays open while the bank identity gate remains unresolved. No three-leaf acceptance or release is claimed.

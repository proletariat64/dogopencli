# Leaf synchronization declarations

A List package opts into durable synchronization with a top-level `sync` array in `leaf.json`. Installation validates every declaration before loading the adapter or creating dataset bindings. Missing declarations mean unsupported; the host does not infer support from names, timestamps or successful temporary-cache publication. Get-only packages cannot declare sync.

Each profile declares:

- `variant`: a unique source variant name, distinct from query date windows.
- `mode`: `settings` for authoritative complete replacement, `runtime` for retained native record history, or `observation` for captured current/daily state. A timestamp does not turn current state into recoverable history.
- `key_fields`: the complete native identity tuple. `scope_parameters` adds only qualified native namespace context, such as account alias for account-local identities. Time-window parameters cannot namespace records. `allow_empty_key_components` is permitted only when the native identity contract explicitly accepts null/empty components.
- `match`, `present`, `absent`: native parameter conditions selecting exactly one variant. `parameters` supplies qualified enrollment defaults; it does not change the native adapter or authorize invented required scope. For example, cash balance date presence selects daily versus latest, while interest-rate source selects four independent variants.
- `time`: native start/end parameter names, `format` (`date`, `compact_date`, `datetime`, or `offset_datetime`), qualified IANA `timezone` or null, upper-bound `end_inclusive` (true/false/null when unknown), native `precision` (`second` or `millisecond`), `max_days`, `overlap_days`, `partitionable`, `follow_supported`, and a human-readable `basis`. The same start/end parameter identifies a single-date snapshot. Following requires a known timezone and qualified partitioning; partitioning requires known boundary semantics. Unknown clocks/boundaries permit only exact explicitly submitted scopes.
- Optional `version_field` and `version_kind` (`number` or `datetime`) establish verified source ordering. Otherwise updates use latest-observed semantics. Do not qualify ordering from the presence of a timestamp alone.
- `evidence`: a concise statement of the native identity and acquisition contract. `unsupported_reason`, when present, identifies the concrete unqualified guarantee and blocks publication. `priority` determines prerequisite acquisition order; it never grants broader source access.

The shared API exposes `profiles(manifest)` and `select_profile(manifest, parameters)` with immutable profile/time dataclasses. Parameter names in declarations use the native CLI hyphen spelling; selection also accepts parser underscore names. Future packages use the same declarations without host leaf-name dispatch.

The [qualification matrix](sync-qualification.md) records the existing source inventory and limitations. It is not production UAT of the importer. Durable acceptance still requires complete acquisition evidence at run time, including required components and identity quality, independently of cache publication policy. Native collectors, date validation, total semantics and request budgets remain authoritative.

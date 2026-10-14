# Composite cash account fields (#162)

Specification: [GitHub issue #162](https://github.com/proletariat64/dogopencli/issues/162).

`dogopencli liquidity cash accounts list` returns one reference account row per validated `(aliasName, currency)`. The shared native cash `id` is not an account join key. Cash, baseline and genuine detail identity fields must agree; no alias-based entity inference is applied. Account information, attached settings and balances remain separate concepts.

The three inquiry-only GET sources are `/queryintnalbkactlist.json` (ordinary page size 5000), `/bankAccountBaseLineQuery.json` (page size 1000), and `/bankAccountBaseLineDetail.json`, on `iliquidity.alipay.com`, tenant `GUAPW3SG`. Baseline commands and standalone cache maintenance are internal only. Sequential details share one authenticated session; stderr reports detail acquisition progress.

| Public fields | Canonical source | Interpretation |
| --- | --- | --- |
| `aliasName`, `currency`, `bankId`, `instId` | Validated source identities | Cross-source values must reconcile. |
| `accountType`, `status` | Baseline list exclusively | `NORMAL` stays `NORMAL`; empty and unexpected native values remain unchanged. No CA/SVF or Norm fallback. |
| `gmtModified`, `operator` | Cash | Cash modification event; baseline/detail events remain source-qualified. |
| Common fields other than cash modification fields | Baseline list | Baseline wins; conflicting cash/detail values remain in metadata. |
| Cash-only account, interest and limit fields | Cash | Preserve null, empty, zero and native decimal representation. |
| Complementary operational, network and blockchain fields | Detail or baseline list | Preserve native nested structures and unknown complementary fields. |
| `detail_state` | Acquisition diagnostic | `succeeded`, `refused` or `missing`. |
| `source_metadata` | Acquisition diagnostic | Source presence, match, per-field provenance, raw sources, collisions and safe detail refusal evidence. |

`source_metadata.raw.cash`, `.baseline` and `.detail` preserve source-qualified native values, including differing modification events. `.provenance` identifies canonical field ownership; `.conflicts` preserves competing source values instead of silently overwriting them. Future shared names follow the same precedence, with identity conflicts remaining hard errors. Successful unknown detail fields enrich the row; the schema is open, and sampled field inventories are not complete native-schema or nullability proof.

Default table columns include account identity, baseline `accountType`/`status`, `timeZone` and `detail_state`. JSON and `--fields` expose the full merged row. Declared local filters, limit and offset apply after acquisition and cannot reduce required source or detail coverage. `--status NORMAL` matches the baseline state. No new native entity filter or public account get is introduced.

List coverage and required detail coverage are independent. Individual native detail business refusals retain list fields with safe error evidence; valid unmatched accounts remain visible and incomplete. Default usable incomplete output returns rows with warnings and exit 0; `--require-complete` rejects missing coverage. Authentication, transport, malformed envelope and identity failures remain hard errors.

A currently verified internal single cash hole may satisfy list coverage with `VERIFIED_BACKEND_HOLE`. Native reported count remains visible alongside effective expected count, unique arrivals and current probe evidence. A persisted offset is only a hint, never completeness proof. It cannot excuse missing details or other leaves' deficits. Live never saves business rows; explicit refresh stores unified rows and evidence in one atomic temporary slot. Offline replay cannot probe or update hints. Old cash-only slots require explicit refresh.

Implementation is tested through public CLI, synthetic CDP and temporary SQLite. Production inquiry-only UAT and a full successful native-detail field inventory remain separate release evidence.

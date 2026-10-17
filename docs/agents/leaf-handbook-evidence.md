# Four-pilot ownership and acceptance evidence

[Spec #255](https://github.com/proletariat64/dogopencli/issues/255) requires one
complete PR for four independent leaf implementations and legacy runtime retirement.
This companion distinguishes implemented ownership, automated evidence, historical
comparison and production acceptance. The final PR records artifact and CI status.

## Business ownership

| Installed leaf | Package-owned behavior | Preserved boundary |
| --- | --- | --- |
| [collection.cost](../../src/dogopencli/leaf_packages/collection/cost/adapter.py) | Verified cost endpoint, fixed request, native parser and item identity. | `itemId`; one 1000-row request with `FUND_IN_CHANNEL_TRANS_FEE`; omitted rows only for proven empty shape; capacity shortfall remains incomplete. |
| [liquidity.reference.entities](../../src/dogopencli/leaf_packages/liquidity/reference.entities/adapter.py) | Entity endpoint/body/envelope, offset paging and native identity. | `instId`, not display `instCode` or historical descriptor `id`; fixed total and page/identity consistency. |
| [payment.sla.baselines](../../src/dogopencli/leaf_packages/payment/sla.baselines/adapter.py) | Native list/detail, supported scope/filter mapping, typed identity and detail validation. | `id`; native `slaBaselineId` detail; legal-entity passthrough is acquisition-only with unproven independent filtering effect. |
| [fx.trade](../../src/dogopencli/leaf_packages/fx/trade/adapter.py) | Native RPC contract, bounded query/date scope, parsing and bounded collector. | No invented identity; `IDENTITY_UNPROVEN` and `TOTAL_SEMANTICS_UNPROVEN`; canonical content detects overlap without deduplicating business records or proving completeness; cached filters remain unsupported. |

[contracts.py](../../src/dogopencli/contracts.py) owns neutral endpoint/result
protocols. [domain_contracts.py](../../src/dogopencli/domain_contracts.py) owns only
identity, verified entry URLs and authentication policy. The generic collector,
restricted transport, errors/serialization, domain controls, current help/GUI,
installed registry/lifecycle, cache and Duckdog remain host services. They must not
load retired business implementations directly or transitively.

## Retirement inventory

Removed 86 old business modules under `src/dogopencli/plugins/`, including its
initializer and four domain registration trees. Removed the ten obsolete source
modules `annotations`, `cached_query`, `catalog`, `describe`, `execution`,
`handler_contract`, `snapshot`, `snapshot_cache`, `table` and `transport.snapshot`.
The public `cli.py` retains current dispatch only; `temporary_query.py` retains
only generic window/freshness helpers. Neutral host protocols and domain/auth
metadata have direct consumers, with no compatibility re-exports or bootstrap.

Removed the two obsolete scripts `build_liquidity_fields.py` and
`prepare_channel_snapshot.py`, the old domain-registration example, 83 old-route
or retired-business test files, and five unreferenced JSON fixtures. Ported valid
request-policy, session/lease, collector/rebuild/deadline, precision and cache
concurrency assertions to neutral synthetic contracts or installed public pilots.
Current help, GUI/editor, lifecycle, cache/result policy and domain/auth suites
remain. The external Duckdog importer/fixture remains a separate offline data
owner; it no longer imports retired query code. Ordinary uninstall retains data.

Static consumer checks and fresh installed execution reject retired imports.
Archive checks cover every retired source module, nested transport snapshot and
both obsolete scripts. Ignored retired bytecode and reviewer-generated adapter
bytecode were removed; a source bundle containing bytecode is correctly rejected,
not silently repackaged. Historical Python remains outside the repository/runtime.

## Verification matrix

| Pilot | Installed synthetic execution | Same-input historical comparison | Nonempty production live/refresh/offline |
| --- | --- | --- | --- |
| collection.cost | Wheel/sdist matrix passed | Exact native fields/types, amounts, item identity and occurrences match | 556 rows; live, accepted refresh and offline native equality passed |
| liquidity.reference.entities | Wheel/sdist matrix passed | 5,003-row paging and native `instId`-only case; 71 production rows match | 71 rows; live, accepted refresh and offline native equality passed |
| payment.sla.baselines | Wheel/sdist list/get/filter matrix passed | Native list (23), real-ID detail and representative filters match | 23 rows; all modes, native get, four supported server filters together and cached filtering passed |
| fx.trade | Wheel/sdist bounded-unknown matrix passed | 52-row paging, duplicate multiplicity, and 166 production rows match | 166 rows over four pages; all modes passed with `complete=false` and unknown identity/total semantics |

Same-input replay ran in separate installed release/new environments. Six positive
cases match typed native row multisets and requests: collection (2 rows), payment
list (2) and detail (1), liquidity (5,003 over two pages), FX paging (52) and
FX multiplicity (3, including two identical occurrences). The seventh case
confirms the explained historical liquidity identity defect: `instId`-only input
fails the old `id` descriptor and succeeds under the current native contract.
Production-response replay additionally fed the identical private captured
responses into separate installed historical/current processes, with network
access denied. All six cases matched typed native records, counts, multiplicities
and request objects: collection 556, liquidity 71, payment list 23, payment detail
1, payment filtered list 1 and FX 166. Liquidity JSON-encoded request objects were
compared structurally. Native fields were not projected away or normalized for
comparison. This is separate from the real production inquiries.

Production UAT ran on 2026-10-17 through a fresh installed wheel outside the
checkout, task-isolated configuration and task-owned Chrome profile on CDP 54395.
Manual SSO and subsequent headless verification passed for every domain. Initial
FX/liquidity readiness timeouts cleared after bounded page warm-up without product
changes. The unfiltered FX one-day request returned native business failure
`IPAY_RS_520000500`; it was never treated as empty success. The previously qualified
2026-10-03 date/BCode/scene/type/fulfillment/currency-pair scope then succeeded.
Exact business identifiers and raw responses remain private.

Every offline list made zero business requests and matched the full native
refresh response, including amounts/types and multiplicities. Display limits did
not truncate acquisition. Payment get used a real listed ID and returned native
detail; representative `biz-category`, `creditor-currency`, `region-code` and
`status` filters were exercised online and offline. Legal-entity filtering effect
remains unproven. No business rows were imported into Duckdog.

Local checks at the corrected source passed: **764 pytest cases and 20 subtests**,
with four opt-in artifact cases checked separately; Ruff, format (163 files),
doc-guard (166 Markdown files) and diff checks passed. A pre-existing fork/thread
DeprecationWarning remains. The corrected pilot/runtime subset passed 73 cases.
Standards, Spec and OCR identified the same single FX 401/403 argument defect;
it was fixed with four public CLI regressions. OCR covered 30 selected files,
then the correction review covered one file with zero findings and no failed
review items. Markdown and deleted files are not represented by that OCR coverage.
The final corrected wheel/sdist pair passed all four explicit gates in 185.18s.
Both fresh installed execution matrices passed, with exact-byte checks matching
52 Python sources and four manifests to corrected source `f3042b4`.

```text
wheel SHA256 245edc9de1a16d11ab84b472b6caee3347524d7e2e6db0b5e84673d4b739bc5c
sdist SHA256 fe5d1cd89a14699962f636b925d5d131699955eb1cb8b9663d5cfb190eba6153
```

These are task-local acceptance artifacts, not a release or installation update.
Later evidence-only Markdown edits leave runtime payloads unchanged. Remote CI
is reported for the final pushed PR revision separately. Distribution proof additionally builds both wheel and
sdist, checks retired-file/import absence, installs outside the checkout without
editable imports, installs all four packages through public commands and executes
their inquiry paths in fresh processes with controlled transport. Module origin
checks and retired-import rejection complement positive execution. Remote CI,
production UAT and release are separate evidence layers.

## Historical comparison and production boundaries

Reference: GitHub release `v0.4.3`, pinned to
`a7e5c5ead675487646eb9a53d73ec9e0aeb944f9`. The source is obtained in an isolated
location outside the repository and new runtime. Replay the same input in separate
historical/new environments, comparing fields, JSON types, exact amounts, identities,
counts and multiplicities. Production observations at different times need not be
byte-identical; pinned source is a reference, not an unconditional correctness oracle.
Native business meaning takes precedence over confirmed historical defects.

The historical liquidity descriptor requires `id`; the current native leaf uses
`instId`. Preserve both native fields when present and report that identity decision
explicitly. FX content equality, repeated occurrences and reported totals never
prove backend identity or completeness. Historical counts are observations, not
acceptance targets. Missing required positive production samples leave acceptance
incomplete.

Use only task-owned configuration/profile and an allowed CDP port, with manual
SSO as needed. Keep raw responses and authentication private; publish sanitized
findings. No production mutation, global installation, release or daily deployment
is part of #255. Ordinary uninstall retains Duckdog and refresh does not import
business rows. State reset is optional and requires a concrete scoped inventory.

## Standard simple-leaf exercise

[examples/leaf_simple](../../examples/leaf_simple/) owns its synthetic endpoint,
request, parser and identity. It imports neutral host contracts and generic
mechanics, without a production business implementation. The endpoint and entry
use `leaf-handbook.invalid`; this is not a fifth bundled inquiry.

[The public CLI exercise](../../tests/integration/test_leaf_handbook.py) covers
directory/ZIP verify/pack/install, declaration-only help/describe, two-page
collection, exact decimal and unknown-field preservation, live without publication,
refresh/offline replay, error/empty/strict rejection retaining prior cache, request
allowlisting and uninstall with retained Duckdog. Its resource variant remains
usable after source deletion via `Path(__file__).parent`. Bare sibling imports
remain unsupported by the installed adapter loader; ZIP payload acceptance does
not prove Python package semantics.

These tests establish the standard development path and the particular auxiliary
loading boundaries exercised. They do not qualify a real endpoint or prove every
complex leaf fits that route. The broader migration map #241 remains paused;
the four pilots now establish the handbook method for their accepted business
boundaries. That evidence does not qualify additional endpoints or complex leaves.

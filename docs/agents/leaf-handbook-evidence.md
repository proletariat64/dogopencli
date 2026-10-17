# Four-pilot ownership and acceptance evidence

[Spec #255](https://github.com/proletariat64/dogopencli/issues/255) requires one
complete PR for four independent leaf implementations and legacy runtime retirement.
This companion distinguishes implemented ownership, automated evidence, historical
comparison and production acceptance. Pending rows are not passing evidence.

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

Retire the old `dogopencli.plugins` business trees and their automatic domain/leaf
registration, static catalog/description/dispatch, obsolete cache-name and snapshot
machinery, old command handlers and unused scripts. Preserve valid new-interface
assertions and re-express necessary native business assertions through installed
leaves; remove tests that require retired routes or bootstrap. Historical Python
is not retained as an archive, renamed implementation or compatibility fallback.
The final PR records the concrete removed-file inventory and consumer checks.

## Verification matrix

| Pilot | Installed synthetic execution | Same-input historical comparison | Nonempty production live/refresh/offline |
| --- | --- | --- | --- |
| collection.cost | Pending final artifacts | Two native rows, exact values/types and requests match | Pending authentication |
| liquidity.reference.entities | Pending final artifacts | 5,003-row two-page equality; native `instId`-only acceptance explains historical `id` difference | Pending authentication |
| payment.sla.baselines | Pending final artifacts; list/get/filter | Two list rows plus detail and supported server filters match | Pending authentication; real-ID get and representative supported filters also required |
| fx.trade | Pending final artifacts; bounded unknown semantics | 52-row two-page equality and three arrivals including an identical duplicate; multiplicity retained | Pending authentication; honest incomplete remains accepted |

Same-input replay ran in separate installed release/new environments. Six positive
cases match typed native row multisets and requests: collection (2 rows), payment
list (2) and detail (1), liquidity (5,003 over two pages), FX paging (52) and
FX multiplicity (3, including two identical occurrences). The seventh case
confirms the explained historical liquidity identity defect: `instId`-only input
fails the old `id` descriptor and succeeds under the current native contract.
This synthetic replay is separate from production UAT.

Required repository gates are focused tests, full surviving pytest, Ruff, format,
doc-guard and code review. Distribution proof additionally builds both wheel and
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
record a proven migration method only after all four pilot gates actually pass.

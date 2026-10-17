# Installed leaf plugins and four pilots

Status: accepted; implements [spec #219](https://github.com/proletariat64/dogopencli/issues/219)
Date: 2026-10-17

## Context

The completed domain foundation owns authentication, domain switches and recorded
operational observations. Business leaves need independent local installation,
one command spelling and common cache/storage/documentation behavior. Keeping old
leaf registration and syntax would leave two active owners of the same inquiries.

## Decision

A configuration owns `plugins/<domain>/<dotted-leaf-name>/leaf.json` and a local
Python inquiry adapter. Folder and declared identity must agree. The global ID is
`domain.name`. Startup discovers valid leaves and reports broken ones independently.
There is no version manager, hot loading or separate leaf enable switch.
Domain enablement and authentication remain authoritative.

All actions follow the domain: `payment list sla.baselines`,
`payment get sla.baselines <id>`, `payment refresh sla.baselines`,
`payment describe sla.baselines`. Help and maintenance use the same dotted name.
Formatted output supports `json` and `text` only. Native business behavior belongs
to each installed adapter. The repository and built distributions do not retain
legacy business implementations or compatibility copies.

Common runtime owns collection orchestration, result policy, one cache slot per
list, rendering and storage registration. Adapters own verified native contracts,
parsing and paging policy. Native business fields retain their values and types.
ADR 0019's usable-incomplete policy remains: warnings and unknown totals/identity
stay visible; strict completeness rejects incomplete candidates.

ADR 0020's single-slot cache behavior remains. A nonempty accepted refresh replaces
the whole saved scope; empty/error/strict rejection preserves it. Live never
publishes. Uniform TTL applies to FX too. Confirmed folder removal cleans only that
leaf's new cache; malformed folders and failed scans preserve it.

Each list registers one configured Duckdog relation. First installation initializes
an empty `_record VARCHAR` table; later loads validate ownership and structure.
Registration is local and acquires no business data. Uninstall retains tables;
reinstall validates them. No import or cache-to-Duckdog population is included.
The effective configuration defaults to a local `duckdog.duckdb` unless
`[duckdog].path` specifies another database. Relation names are manifest bindings,
not inferred from user-facing business fields.

One basic manifest schema supplies help, description and localhost form fields.
The form edits documentation prose, meanings, units and examples. Technical
identity, operations, parameter contracts and native record identity are locked.
Preview shares the CLI renderer. Save validates, detects stale edits and atomically
replaces the manifest; there is no autosave or live reload. Existing loopback,
Host/Origin and mutation-token protections apply.

## Consequences

This supersedes ADR 0021's static leaf contributions, legacy compatibility and
per-leaf enable requirements for installed leaves, preserving its domain/auth/
browser/state foundation. It expands the GUI from inventory to documentation
editing. It extends ADR 0020's external read-only Duckdog boundary only to empty
initialization and binding validation; imports/history remain separate.

The pilots are payment `sla.baselines` list/get, collection `cost` list, liquidity
`reference.entities` list and FX `trade` list. Four-domain production UAT and
GUI interaction evidence are required independently of automated checks. FX's
166-row reference reproduction is comparison evidence, never a fixed future count
or proof of completeness. The broader migration map #241 remains paused.

## Amendment: independent business implementations (#255)

[Spec #255](https://github.com/proletariat64/dogopencli/issues/255) replaces the
four pilot wrappers and retires the host's legacy business bootstrap. Neutral
endpoint/result protocols belong to `dogopencli.contracts`; domain-only identity
and authentication declarations belong to `dogopencli.domain_contracts`. Neither
owner registers business implementations. Current CLI/help/GUI/registry consumers
use those owners directly, with no compatibility re-exports.

The four adapters own native request construction, response validation, identity,
filters and collection policy. Genuine shared transport, collection/evidence,
serialization, lifecycle, cache and Duckdog services remain host-owned. Unmigrated
leaves do not justify shipping the old runtime or a renamed copy.

Historical business comparison uses isolated release `v0.4.3`, pinned to
`a7e5c5ead675487646eb9a53d73ec9e0aeb944f9`, outside the repository and new
runtime. Compare identical inputs, field values/types, amounts, identities, counts
and multiplicities. Liquidity retains native `instId` despite the old descriptor's
`id`; FX content comparison never proves native identity or total semantics.

Acceptance requires both architecture and business proof: retired files absent
from repository/wheel/sdist, fresh installed execution outside the checkout,
all four packages through public lifecycle and controlled transport, required
checks/review, same-input comparisons and four-domain nonempty production UAT.
Payment additionally requires real-ID get and representative supported filters.
The evidence companion records results; this decision alone is not a passing gate.
Daily installed versions remain untouched. Delivery ends at one reviewable PR,
without automatic merge, release or deployment.

## Amendment: explicit portable installation (#239)

The general lifecycle in [spec #239](https://github.com/proletariat64/dogopencli/issues/239)
extends directory-only pilot delivery. `plugins install` accepts one local
directory, ordinary ZIP, direct HTTP(S) ZIP, or explicit `bundled:domain.name`.
One shared static validator checks root layout, manifest, adapter presence and
bounded safe payloads without executing adapters. Installation then checks the
adapter interface and host-owned storage bindings before publishing an independent
snapshot. Duplicate identities are rejected; reinstall is uninstall then install.

The four bundled leaves are application resources available for explicit install,
including from an installed wheel. Discovery and progressive help read declarations
without adapter execution, storage initialization or lifecycle reconciliation.
The former `plugins install-pilots` copying entry point is removed. Availability,
installation and production qualification remain separate facts.

Lifecycle operations synchronize filesystem publication, binding history and cache
ownership. Uninstall accepts the global identity, works for broken or disabled
leaves, and is idempotent only when absence is established. It removes the installed
directory and owned temporary cache, preserving Duckdog data and ownership for
compatibility validation on reinstall. Older refreshes cannot republish removed
cache. Domain enablement, credentials and inquiry-only execution remain host-owned.

A repository `plugin-helper` skill exposes local static verify/pack scripts using
the same validator. Pack validates before and after ZIP creation and refuses output
overwrite or source self-inclusion. Runtime checks and production UAT remain
separate acceptance gates. This amendment permits portable package lifecycle only;
versions, updates, dependency resolution, catalogs and automatic installation
remain outside scope. ADRs 0019 and 0020 retain their result/cache semantics.

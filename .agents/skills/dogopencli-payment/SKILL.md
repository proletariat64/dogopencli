---
name: dogopencli-payment
description: Query installed payment SLA baseline lists and native details through dogopencli. Use for payment SLA configuration lookups or comparisons, including 付款SLA基线; supports offline, explicitly requested live, and refresh inquiries.
---

# Dogopencli payment inquiries

Use the public CLI for inquiry-only access. This skill does not authorize
production configuration changes. The bundled payment leaf is `sla.baselines`
with list/get. Historical channel/cost commands are not current registrations.

## Discover the installed contract

Use installed `dogopencli`; in this checkout use `uv run dogopencli`. If unavailable,
report the missing executable rather than installing implicitly. Apply the host's
shell wrapper convention, such as `rtk proxy`, to these examples.

Start with `dogopencli payment -h`, then `payment list -h` and
`payment list sla.baselines -h`. Use current JSON help for flags, constraints,
effects and examples. Help is flag-only. Bare groups disclose navigation;
bare executable leaves run inquiries. If the leaf is absent, report that fact;
installation requires task authorization and is not inferred from lookup intent.

```bash
dogopencli payment list sla.baselines
dogopencli payment list sla.baselines --live
dogopencli payment get sla.baselines BASELINE_ID
```

Obtain a native `id` from the list before get. The detail endpoint uses
`slaBaselineId`; a list row is not a substitute for native detail.

## Select scope and data mode

Default list replays the temporary cache without browser/network access. Use
`--live` for an explicitly current/backend request; it does not publish cache.
Use `payment refresh sla.baselines` only when updating the saved snapshot is
within the task. A successful nonempty accepted refresh replaces the whole slot;
empty, failure and strict rejection retain the prior snapshot.

Supported native filter mappings are `--biz-category`, `--creditor-currency`,
`--region-code` and `--status`. Read installed help for exact accepted values and
mode restrictions. `--biz-legal-entity` is acquisition-only, has no cached field
mapping, and its independent backend filtering effect is unproven. Disclose that
limitation rather than asserting a verified legal-entity subset.

## Interpret evidence

Use JSON for parsing and inspect `data`, `meta`, `error` and exit status. Current
formats are `json` and `text`. Discover display windows in current help; use
`--limit 0` for an unrestricted display when accepted, without treating that
option as backend completeness. Select `--fields` only for observed native names.

Report source, capture time, saved query scope, staleness and completeness.
Use `--require-fresh` or `--require-complete` when the conclusion requires them.
Native SLA values are configuration targets, not measured payment performance.
Preserve exact numeric/text amounts, unknown fields and null/empty distinctions.
An empty cached filter result proves only no match in the saved records.

## Recover within scope

For `CACHE_MISS` or `CACHE_CONTRACT_CHANGED`, inspect refresh help and refresh
when authorized. Do not convert an old snapshot to bypass contract validation.
For authentication/browser failures, use `dogopencli auth check --domain payment`
and authorized `dogopencli login --domain payment`; manual SSO belongs to the
user. Follow repository browser/profile rules; never use ports 9330–9340 or
borrow another session.

Report persistent errors and available evidence rather than retrying indefinitely
or bypassing the CLI with arbitrary requests/JavaScript. Keep cookies, tokens and
unrequested sensitive data out of logs. Save requested exports under a persistent
user-selected path or private repository `tmp/`. HTTP 200 and returned rows alone
never prove a successful business inquiry or complete coverage.

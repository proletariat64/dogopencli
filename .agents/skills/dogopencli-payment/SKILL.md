---
name: dogopencli-payment
description: Query payment channel configurations, channel costs, and SLA baselines through dogopencli. Use for payment operations lookups or comparisons, including 付款渠道、成本、SLA基线; covers cached, mock, and explicitly requested live inquiries.
---

# Dogopencli payment inquiries

Use the public CLI for inquiry-only access. This skill does not authorize changes to production configuration. Payment rules and collection products are outside this command set.

## Discover the relevant command

Use installed `dogopencli`; in its checkout use `uv run dogopencli`. If unavailable, report the missing executable rather than installing dependencies implicitly. Apply the host's shell wrapper convention, such as `rtk proxy`, to these examples.

Start with `dogopencli payment --help`, then inspect an action such as `dogopencli payment list --help` and the relevant installed dotted leaf with `-h` or `--help`. Help is flag-only; positional `help` commands are unsupported. Bare root and groups disclose navigation; bare executable leaves run queries. Read current JSON help for accepted flags, constraints, effects, and examples instead of inventing filters or copying backend requests.

| Need | Command |
| --- | --- |
| Channel configuration | `dogopencli payment channel list` |
| Payment channel costs | `dogopencli payment cost list` |
| SLA baseline discovery | `dogopencli payment sla baselines list` |
| Baseline details | `dogopencli payment sla baselines get --id ID` |

Get an SLA ID from the list, then request detail; a list row is not a substitute for detail. Cost configuration alone does not establish actual transaction charges or aggregate expenditure.

## Choose data and scope

Default queries read the local cache without browser or network access; local initialization or migration can write files. Use this default for ordinary lookups. For an explicitly current/backend request, inspect leaf help and use `--live`, or refresh if the user requested updating the local snapshot. Live queries do not refresh cache.

Channel defaults to EXTERNAL. Other advertised payout scopes require a source supporting them. A configured snapshot source covers EXTERNAL only and cannot serve live queries; do not switch source configuration merely to make a query succeed.

Cost is restricted to FUND_OUT_CHANNEL_TRANS_FEE. SLA `--biz-legal-entity` is live-only and its independent filtering effect is unverified: disclose this limitation rather than claiming a verified legal-entity subset.

## Query and interpret

Keep JSON for parsing; inspect `data`, `meta`, `error`, and exit status. Help uses JSON/text; business results use JSON/table. Apply filters from the leaf contract. Repeated values of one cached filter are OR, different fields are AND; live filters accept one value per field.

Default list output is at most 100 rows. For totals, exports, or exhaustive comparisons, use `--all` or traverse the advertised output window, checking metadata. Do not combine `--all` with explicit `--limit` or `--offset`. Select `--fields` only after discovering actual returned field names.

Report source, capture time, scope, staleness, and completeness with conclusions. Default TTL is 72 hours, configurable; use `--require-fresh` and/or `--require-complete` when the requested conclusion requires them. Output truncation, snapshot completeness, and backend completeness are different conditions.

Channel mock data can be a complete curated dataset while `simulated=true` and `backend_complete=false`. Describe it as exported/mock evidence, not current full production coverage. An empty result from partial coverage proves only no match in available records. `seqid` is a local dataset position, not a stable business key; do not use it to join snapshots or domains. Establish a shared business key before comparing channel, cost, and SLA records.

## Recover within scope

For CACHE_MISS, inspect `dogopencli payment refresh DOTTED_LEAF --help` and refresh when within the requested task. Refresh writes local snapshots; its source may be an export or CDP. Preserve existing source configuration and let the CLI enforce publication quality.

For AUTH_REQUIRED or BROWSER_UNAVAILABLE, inspect `dogopencli auth --help` and the relevant auth leaf. Use the existing session check first; use `dogopencli login` when login is needed and authorized, leaving interactive SSO to the user. Keep DI-compatible auth arguments as advertised by current help. Never use CDP ports 9330–9340.

On persistent collection or source errors, report the error and available coverage; do not loop indefinitely or bypass the CLI with arbitrary CDP JavaScript or backend requests. Keep cookies, tokens, and unrequested sensitive record content out of logs. Save requested exports under a persistent user-selected path or repository `tmp/`, not system `/tmp`.

Finish with the requested findings and their material data limitations, or the precise blocker and next command. Never infer success solely from an HTTP status or the presence of some records.

# Operation rules

Independent `liquidity.rules.operation` package for inquiry-only operation rules.
The host wheel does not bundle this package.

Install this directory or its verified ZIP with `dogopencli plugins install`.
Use `dogopencli liquidity list rules.operation` for the saved snapshot,
`dogopencli liquidity list rules.operation --live` for acquisition without publication,
and `dogopencli liquidity refresh rules.operation` to replace the saved snapshot only
when the candidate passes host quality policy. Refresh never imports into Duckdog;
use the explicit importer separately.

Native list: `GET /riskActionRuleListQuery.json`, `rowStart` offsets,
`pageSize=1000`. Inquiry is encoded in the JSON string `riskActionRuleListQueryVO` with the fixed GUAPW3SG tenant both inside and outside the inquiry.
Native `ruleId` is retained with its original JSON type. Full records retain
unknown fields and exact decimals. No page echoes exist; completeness requires a
stable total and agreement of arrival and unique identity counts.

The manifest selects the host List SDK: general provider, native offset paging
and the declared native identity/width. The leaf builds requests and parses native
responses; the host owns the collection loop and quality evidence. Duplicates,
conflicts and short or empty interior pages remain incomplete. Conflicts retain
the last arrival without claiming it is newest. Strict queries and refresh reject
incomplete acquisitions; empty or failed refresh preserves the preceding snapshot
and capture time.

`--status` selects exact native `ruleStatus` locally; repeat it for alternatives. Filtered refresh retains all native records.

The pinned v0.4.3 release establishes historical provenance. Production UAT and
same-input replay qualify current behavior separately; synthetic tests alone do
not establish production acceptance.

Native detail: `GET query /riskActionRuleDetail.json` with string `ruleId` and GUAPW3SG tenant.
Run `dogopencli liquidity get rules.operation RECORD_ID`. The response must echo
`ruleId` by string equivalence, preserving its native JSON type. Get performs
a real detail inquiry and never publishes or changes the saved list.

Use the native List `ruleId` value for this lookup. Get retains one native root
response, including nested and unknown fields; separate history, logs and child
pages are unqueried.

```bash
dogopencli liquidity list rules.operation --live --with-detail --offset 0 --limit 1
```

This queries detail only for selected List rows and returns separate `record` and
`detail` members in List order. `--limit 0` selects all remaining matching rows
within execution bounds. Any detail failure fails the combined query; successful
details do not upgrade List completeness. Neither direct Get nor this mode changes
the saved List or imports into Duckdog.

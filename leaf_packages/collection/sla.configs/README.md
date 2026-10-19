# sla.configs

Inspect collection SLA configuration targets through standard List/Get SDK:

```bash
dogopencli collection list sla.configs -h --format text
dogopencli collection list sla.configs --live --limit 0 --require-complete
dogopencli collection refresh sla.configs --require-complete
dogopencli collection get sla.configs CONFIG_ID
dogopencli collection list sla.configs --live --with-detail --limit 1
```

List sends JSON POST `/api/fundInSlaConfig/search.json` to
`iglobalfundcontrol.alipay.com` with only `pageNo=0,pageSize=1000`. Native page
echoes, total and unique string IDs must agree. Width1000 is qualified, not a
maximum-capacity claim. An explicitly successful zero-total response may omit
its List; null is not that exception. Output orders ASCII digit IDs by numeric value, breaking ties by the original
string, then other IDs lexically; returned IDs remain unchanged strings.

Get sends only `slaConfigId` as GET query to
`/api/fundInSlaConfig/getDetailBySlaConfigId.json`. Its independent `resultData`
root must echo that identity and contain the required SLA business fields.
`holidayLimit` may be null; nonnull settings require string arrays `currencyCodes`
and `regionCodes`. Full native values, unknown fields and nested order survive.
List-only `viewProcessInstanceRequired` is not synthesized into detail.

The four local filters are exact case-sensitive matches: `--business-line`,
`--entity`, `--currency`, `--region`. Repeated values OR, dimensions AND; commas
and `*` are literal and blank inputs fail. Filtering precedes windows/projection.

`--with-detail` fetches detail only for the selected live List window and returns
separate `record`/`detail` roots. Get and composition preserve saved Lists and
write no business cache or Duckdog data. SLA targets are native configuration,
not measured performance or locally calculated arrival times.

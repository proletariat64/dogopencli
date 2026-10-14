# Interest-rate source inquiries

Specification: [#178](https://github.com/proletariat64/dogopencli/issues/178).
Delivery tracker: [#170](https://github.com/proletariat64/dogopencli/issues/170).

One command group owns four fixed native list contracts. Source selects a
contract, not an arbitrary backend parameter or endpoint.

| Source | Kind | Native identity | Date semantics |
| --- | --- | --- | --- |
| `market` | `runtimes` | currency, rateName, ratePeriod, effectiveDate | Existing market observation window; compact native dates |
| `bank` | `runtimes` | bankId, currency, productTerm, productType, quoteDate | Explicit paired ISO request dates; compact native quoteDate |
| `expectation-rule` | `settings` | ruleId | Configuration validity, not an observation window |
| `expection` | `settings` | ruleId | Configuration validity, not an observation window |

The spelling `expection` is intentional. Only this source has genuine native
detail. Other source getters refuse with `UNSUPPORTED_CAPABILITY` before
querying the source.

```bash
dogopencli liquidity investment interest-rates --source market list --live
dogopencli liquidity investment interest-rates list --source market --live
dogopencli liquidity investment interest-rates --source bank list --live \
  --from-date 2026-09-14 --to-date 2026-10-14
dogopencli liquidity investment interest-rates --source expectation-rule list --live
dogopencli liquidity investment interest-rates --source expection list --live
dogopencli liquidity investment interest-rates --source expection get --id NATIVE_RULE_ID
dogopencli refresh liquidity investment interest-rates --source expection
```

Online list, refresh and get require an explicit recognized source. The same
source at both positions is accepted; conflicting sources fail before requests.
Bank requires both date bounds and uses only the verified GMT+08 timezone.
Rules reject observation-date arguments. Market preserves its existing default
window and currency filtering. Configuration statuses, including invalid
rules, are retained.

All list contracts use their own fixed POST JSON template and exact native
success, array and total paths. External detail sends its string identity in
the POST query with an empty business body; the response must repeat ruleId
and belong to the external-rule category. Private request templates and
production examples remain in the authorized requirement records.

Bank's reported total counts quote-date groups, while each group can contain
multiple product rows. The reported total and unit remain separate from
acquired rows and unique identities. Arrays exceeding the requested group
page size are never truncated. Missing group pagination or product-coverage
proof produces an explicit usable partial result, never an invented row total.

Raw `rateValue` and `ruleValue` strings keep precision, negative values, zero,
empty strings and null. Source displays do not establish a universal scale;
the CLI does no multiplication, division, yield calculation or normalization.
`quoteDate`, source modification time and capture time remain distinct.

External detail retains the native fields and nested effect-date values,
operation logs, attachment lists/maps and previous detail objects. It performs
one detail inquiry, without recursive reads or attachment downloads. A rule's
test label does not establish a real market forecast.

ADR 0019 applies: valid incomplete acquisitions return warnings and
`complete=false` by default; `--require-complete` rejects them without data or
publication. Authentication, transport, business, parsing and identity failures
remain hard failures.

ADR 0020 applies: all sources share one temporary list slot. A nonempty refresh
atomically replaces its saved source, scope and quality. Empty, failed and
strict-rejected refreshes preserve the previous slot. Live and get never write
the slot, and refresh never acquires details. Offline no-source replay reports
the saved source and kind; an explicit mismatched source is refused. Unknown
legacy source identity requires explicit refresh, preserving existing bytes.
Prune affects only this logical list slot. External duckdog datasets are outside
this change.

## Implementation UAT, 2026-10-15

An isolated new profile completed human SSO and automatic headless
re-verification on permitted loopback CDP port 9229. No authentication state
was copied from another profile. Public CLI inquiries produced these results:

| Inquiry | Scope | Observed result |
| --- | --- | --- |
| Market list | 2026-10-15 through 2027-01-15 | 2 rows; runtime kind; strict complete |
| Bank list | 2026-09-15 through 2026-10-15 | 51 product rows, 17 reported quote-date groups; runtime kind; strict complete |
| Customized rule list | Registered customer-rule category, all statuses | 4 rows; settings kind; strict complete |
| External rule list | Registered institution-rule category, all statuses | 3 rows; settings kind; complete |
| External rule get | One identity from the same-run list | 27 native fields, matching rule identity/version and external category |

Independent native bank requests at group offsets 0, 10 and 16, widths 10,
10 and 1, returned 30, 21 and 3 product rows. Their union and final-page subset
agreed with the 1000-group response. A boundary request at offset 5 also agreed
in complete product content. The reported group total stayed 17, native dates
were descending, and there was no first/middle-page identity overlap. The
source's echoed pagination fields were zero and were not used as coverage
proof. This verifies the named group contract for the observed scope; it does
not establish a fixed product count per date or a universal rate scale.

Independent market and rule requests at width 1000 and width 1 agreed in
identity, offset order and content, with stable reported totals. The market
result describes its registered source scope, not unqueried rate categories.
Historical sample counts are not permanent expectations.

The existing market syntax, repeated equal source, projection, limit and
offset also passed. External refresh published its isolated temporary slot;
no-source replay reported the saved settings source, and an explicit market
request refused that slot. Production observations remain private; this
record contains only scopes, aggregate counts and contract evidence.

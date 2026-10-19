# rules.same_bank_transfer

List same-bank transfer decision-rule configurations:

```bash
dogopencli payment list rules.same_bank_transfer -h --format text
dogopencli payment list rules.same_bank_transfer --live --limit 0 --require-complete
dogopencli payment refresh rules.same_bank_transfer --require-complete
dogopencli payment list rules.same_bank_transfer --bank BANK_ID --status STATUS
```

The host SDK sends one JSON POST to
`https://ifundboss.alipay.com/payout/api/bookDecisionRule/search.json`, with only
`pageNum=1,pageSize=1000`. Both success envelopes, page echoes and native totals
are validated. Truncation, duplicate identities and capacity gaps prevent publication.
Width1000 is qualified, not a maximum backend capacity claim.

Native nonnegative integer `ruleId` retains exact precision and numeric order.
All fields, including unknown extensions, nested patterns and entity codes remain
unchanged. Patterns are configuration text, not executed against accounts.

`--bank` matches `debitInstId`; `--status` matches `ruleStatus`. Filters apply
locally before windows/projection: repeated values OR, dimensions AND. Matching
is exact and case-sensitive; commas and `*` are literal, blank inputs fail.
No backend business filters, transfers or separate detail inquiries are performed.

# Account-isolation configuration snapshots

Account-isolation queries use an independent source and snapshot, a verified
single page at pageNo=0/pageSize=1000, and raw string identity. Rows must equal
totalCount with unique IDs; totalPageNo is observed to remain zero and cannot
determine coverage. Overflow fails without fallback. The exact explicit
null-list/all-zero empty shape is accepted only for this verified envelope.
See the [contract](../research/general/2026-09-27-collection-account-isolation-contract.md).

All eight filters use local whole-string equality before sorting and windowing.
Customer tags and currency can contain commas; backend matching returns broader
results than exact equality. We preserve raw strings and use one predictable
cached/live filtering contract rather than claiming unverified backend matching.

Bank-account VA rules remain blocked under #52: revalidation reproduces partial
coverage at multiple UI page sizes. Its numeric identities and failing envelope
are not substituted into this account-isolation capability.

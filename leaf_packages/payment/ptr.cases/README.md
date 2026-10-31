# Outflow PTR case library

`payment list ptr.cases` reads the outflow case library through the standard host
multi-source SDK. Each operation acquires the same fixed page0/5000 twice, validates
complete coverage and unique native `id`, and compares sorted retained content.
Both required sources share a 120-second deadline and two-logical-page budget,
including bounded retries. Their independent acquisition evidence survives replay.

The output preserves the assigned case/baseline/money whitelist, including native
amount precision and nullable values. Local filters select exact whole strings:
OR for repeated values, AND across fields. Filtering follows full stability proof.

Live does not publish; only complete nonempty refresh publishes an offline capture.
Incomplete, unstable, failed or empty refresh preserves the previous capture.
No trial, execute, mutation, Get or backend filter is exposed.

The native GET response declares top-level boolean success, resultDataList, exact
page echoes and integer totalCount. Full-page coverage requires the native count
to equal the number of unique case identities; both retained projections must
remain equal before output.

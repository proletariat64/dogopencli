# investment.settlement

Query Cash Base Yield independently through `/cashBaseList.json` with explicit inclusive
`--from-date` / `--to-date` in YYYYMMDD format. The native date axis is
`settlementDate` in GMT+08. The standard List SDK owns pagination and completeness;
the leaf preserves every native record and unknown field without parent assembly.

The manifest declares calendar history; leaf codecs convert public compact dates
to/from the host ISO boundary. Exact observations can be exported and preserved
independently. Cross-window equivalence, deletion and merged publication are not
declared.

This is Cash Base Yield, not a general investment settlement ledger. No
unverified investment ID request filter is exposed.

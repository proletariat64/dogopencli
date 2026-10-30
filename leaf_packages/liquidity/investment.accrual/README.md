# investment.accrual

Query Accrual Base Yield independently through `/accrualBaseList.json` with explicit inclusive
`--from-date` / `--to-date` in YYYYMMDD format. The native date axis is
`transactionDate` in GMT+08. The standard List SDK owns pagination and completeness;
the leaf preserves every native record and unknown field without parent assembly.

The manifest declares calendar history; leaf codecs convert public compact dates
to/from the host ISO boundary. Exact observations can be exported and preserved
independently. Cross-window equivalence, deletion and merged publication are not
declared.

Optional repeated `--investment-no` filters the native accrual request.

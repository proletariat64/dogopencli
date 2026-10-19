# Investment quote groups.

## Native detail

Physical version-row id from the native page/history, sent as quotationGroupId; never the business quotationGroupId. Selected native physical version root and already-returned contacts/history stay intact. No latest-version selection, recursive history acquisition, attachment download or List.

```bash
dogopencli liquidity get investment.quote_groups PHYSICAL_ROW_ID
```

One POST form `/queryQuotationDetail.json` request returns `data`. Preserve the whole native root, including unknown fields, exact values and nested arrays. Missing/malformed roots, business rejection and identity/context contradictions fail; no unverified not-found mapping, child/history acquisition, cache write or Duckdog import.

Native `id`, business `quotationGroupId` and `version` are distinct. Already-returned history stays native even if it contains newer versions; no latest-version choice or recursive acquisition. This package has no List or dataset storage.

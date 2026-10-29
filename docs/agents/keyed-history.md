# Scoped keyed history

`workflow import plan --export EXPORT_ID --action keyed` compiles an offline
incremental reconciliation. `workflow import apply --plan IMPORT_PLAN_ID` applies
it. `workflow current show --export EXPORT_ID` reads the reconciled namespace;
`workflow observation show --export EXPORT_ID` reads the unchanged exact input.
Absent records remain in history. Reapplying the same exact export is a no-op,
even after later imports or regeneration of the import plan.

The exporter freezes an optional leaf adapter's `keyed_contract(parameters)` into
the exact artifact. Import never loads the adapter or derives native facts. The
contract declares:

- `identity`: nonempty native scalar field names identifying one business record.
- `namespace`: meaningful business filters and variant identity. Environment,
  leaf and operation are added by the host. Include an account/tenant namespace
  when identity alone cannot distinguish those records. A requested date window
  is not a namespace for genuinely mergeable history.
- `cross_range_equivalence: true`: explicit native evidence that the declared
  identity refers to the same record across selected ranges.
- `ordering`: either `{"mode": "latest_observed"}` or a reliable source version,
  for example `{"mode": "source_version", "field": "revision", "comparison":
  "numeric"}`. `lexical` comparison requires a native sortable string contract;
  a date-looking value does not establish that guarantee.

Unknown identity, missing source versions, conflicting duplicate identities,
unknown cross-range equivalence and ambiguous ordering block keyed merge with an
explicit diagnostic. `--action preserve` remains available for a complete exact
observation. The native cash balance range contract currently declares
cross-range equivalence unverified; its existence alone does not qualify keyed
merging.

A reliable older source version cannot regress a retained record. Different values
with an equal version fail explicitly. Latest-observed ordering uses export capture
completion, retains the winning export identity and capture time, and makes no
source-newest claim. Identical values stay unchanged while a later capture advances
the observation ordering boundary. Captures with equal ordering and different
values conflict. Independent account identities and native variants remain isolated.

Plans show the native namespace, existing/current counts and inserted, updated and
unchanged counts. Apply recomputes decisions under the writer lock; preview counts
can change after another committed import. Current records, the saved observation
and the action receipt commit together. A failed receipt or row write rolls back
all effects. Exact artifact comparison protects replay without adapter hashes.

Current keyed ownership and full/range replacement ownership cannot yet be mixed
within one registered relation: their equivalence is not established. A conflicting
action fails locally and preserves current data; use preserved observations or a
separately registered destination. This conservative guard also protects unrelated
scope occurrences whose equality does not prove shared ownership. Ordinary keyed
namespaces and account identities coexist in a keyed-owned relation.

# Frozen acquisition repair

Repair freezes the original plan, its acquisition state and the exact complete
baseline exports. It creates separately identified query packages for the uncovered
ranges, including omitted interior work below a newer completed date. The baseline
plans and exports remain unchanged. Native filters, environment, range boundaries
and time meaning come from the original query contract.

```bash
dogopencli workflow repair plan --plan ORIGINAL_PLAN_ID
dogopencli workflow repair show --repair REPAIR_PLAN_ID
dogopencli workflow export run --plan REPAIR_PLAN_ID
dogopencli workflow import plan --repair REPAIR_PLAN_ID --action preserve
dogopencli workflow import apply --plan IMPORT_PLAN_ID
```

Each command executes only its stage. Repair planning is offline and creates only
plan state. Export executes new inquiries and retains each attempt. Successfully
completed repair packages are reused by later explicit runs. Independent successful
baseline exports are never queried again by repair. Failed or incomplete repair
work remains visible and produces an aggregate incomplete outcome.

Gap windows require the leaf's explicit native window permission. Overlapping
baseline inputs are rejected rather than silently selecting the newest export.
Without a safe range contract, retry the unchanged full query. A failed or
incomplete full observation is repaired as a new full capture; records from
different incomplete captures are never stitched into a complete observation.

The import plan selects exact compatible complete baseline and repair exports and
freezes their values. Repair reconciliation preserves separate observations; it
does not infer keyed identity or replacement coverage. Choose an individual exact
export for a separately supported current-data action. Applying the repair import
plan is fully offline. Every observation and receipt commit together, independent
successful observations survive a later failure, and replay uses database receipts
without duplicating observations. No current rows or unrelated observations change.

`repair show` and `status.repairs` report frozen baseline gaps separately from new
repair outcomes. They perform no acquisition or storage initialization. Advancing
the original plan later does not change an existing repair's baseline selection.

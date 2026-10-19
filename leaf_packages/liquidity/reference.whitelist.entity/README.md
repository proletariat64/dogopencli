# Entity whitelist

List uses one independent native GET inquiry with fixed tenant GUAPW3SG and
JSON-string `instFilterConfigQuery`: tenant, lowercase timezone GMT+08, rowStart
and pageSize. Qualified offset widths are 5000 then 1000, not measured maxima.
Native inner/outer counts must agree; SDK identity and page checks gate coverage.
No page echo, currentArea, entity-directory join or latest-record model is assumed.

Optional local `--entity`, `--financial-code` and `--status` match exact values.
Repeated values OR; different fields AND. Status selection accepts VALID/INVALID;
all raw statuses remain visible by default. Missing/null values never match,
commas and `*` are literal, blank inputs reject and accepted values are unchanged.

Full native rows retain arrival order, nested structures and precise values.
Absent/empty tenant echoes are preserved; contradictory present tenant fails.
Live never publishes; failed, empty or incomplete refresh preserves saved data.
This leaf provides no Get, mutation, relationship lookup or Duckdog import.

# System information panel prototype

Question: which arrangement makes read-only configuration, installation, temporary
Cache and retained Duckdog data easy to inspect within the existing workspace?

This is a throwaway interaction prototype with synthetic data. It does not read
configuration or databases and does not implement the production System API.

Open [the standalone HTML](../../../src/dogopencli/gui_system_prototype.html), or
run from this branch's checkout:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory src/dogopencli
```

Then open `http://127.0.0.1:8765/gui_system_prototype.html?variant=A`.

## Confirmed interaction

- A separate System entry in the left navigation replaces the right workspace
  with a System information panel when selected.
- A statistics box sits above configuration, installation, Cache and Duckdog.
- Cache and Duckdog support summaries and expandable leaf/dataset metadata.
- The panel is read-only and never displays individual business records.

## Layout alternatives

- A: cards, with configuration and installation side by side and full-width
  storage sections below. Recommended starting point.
- B: a continuous report with an information directory and full-width sections.
- C: category tabs below the same statistics box, showing one category at a time.

The floating prototype bar switches variants with arrows or the left/right keys.
The URL preserves the selected view, variant and example-data state.

## Sample-data boundaries

Cache counts refer to the latest saved snapshot per List leaf, not business totals
or historical datasets. TTL status is distinct from business-data freshness.
Get-only leaves do not contribute List cache entries.

Duckdog examples cover the current workspace's bound leaf datasets, including a
dataset retained after uninstall. They omit unrelated database tables and business
rows. Exact production statistics, row-count cost and catalog implementation are
still open implementation questions.

The state selector demonstrates available metadata, no saved data and unavailable
metadata. Unavailable values appear as a dash instead of zero. The reread button
only redraws example data. File sizes and paths are illustrative.

## Review assets

- [A: cards](system-A.png)
- [B: report](system-B.png)
- [C: tabs](system-C.png)
- [Expanded storage metadata](system-expanded.png)
- [Narrow-screen layout](system-mobile.png)

No layout verdict has been recorded yet. The prototype stays on its own branch
until the maintainer reviews it.

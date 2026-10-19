# Scope and sample examples

All identifiers and data here are synthetic. These examples illustrate proposals;
they are not HIL acceptance or current production contracts.

| Request | Proposed judgment | HIL decision |
| --- | --- | --- |
| Preserve a pool List whose native rows already contain members and rules | simple | Accept native scope and nested preservation. |
| Deliver prefund List only; frontend links to separate history | simple | Surface history candidate; accept exclusion or discuss expanded scope. |
| Deliver a complete prefund object including separately queried history | complex | Accept experiment scope, then verify parent mapping, child identity, coverage and output at HIL②. |

For the third request, a UI passing `businessNo` into history is a candidate
mapping. A parent's List total does not prove history completeness. An empty UI
array does not establish an executed, successful empty history inquiry. If the
standard SDK cannot perform the required acquisition, report the execution gap
with the accepted spec; do not supply pretend working enrichment code.

## Minimal native-preservation sample

Run this from the repository root with the project Python. It exercises the
existing standard adapter, including business-envelope validation; it performs
no network calls. Change native mapping only after qualifying the actual endpoint.

```python
import runpy

from dogopencli.jsonutil import canonical

sample = runpy.run_path("tools/leaf-dev/example/adapter.py")
native = {
    "success": True,
    "pageNo": 0,
    "pageSize": 2,
    "total": 1,
    "rows": [
        {
            "id": "pool-demo",
            "members": [{"id": "member-demo", "rules": [{"id": "rule-demo"}]}],
            "unknownNativeField": {"amount": "12.3400"},
        }
    ],
}
page = sample["CAPABILITY"].parse_page(canonical(native).encode("utf-8"))
assert page.records == native["rows"]
assert page.records[0]["unknownNativeField"]["amount"] == "12.3400"
```

The adapter returns original native rows; no flattening, fanout or invented
parent/child IDs is necessary. The real leaf still needs its own verified
contract, native identities, pagination and acceptance through leaf-dev.

## Concise spec output

Use only sections relevant to the accepted scope:

```text
Leaf / operations / accepted scope:
Record grain and native identities (parent versus child):
Accepted relations / field mappings / source-native versus constructed shape:
Output example (synthetic) / unknown-field preservation:
Acquisition / dates / per-source pagination and completeness:
Failure versus unknown versus confirmed empty:
Evidence / counterexamples / actual HIL reply references:
Unresolved candidates / implementation gaps:
Acceptance criteria / minimal sample reference:
Final user choice: continue or end (leave unset until answered)
```

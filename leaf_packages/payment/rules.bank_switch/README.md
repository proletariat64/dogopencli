# Payment bank-switch rules

List source nodes from one verified GET query at pageNo0/pageSize1000. Native
totalCount and unique string switchNodeCode establish coverage; totalPageNo is a
known zero placeholder. Width1000 is qualified, not a measured backend maximum.
Overflow, duplicate identities and incomplete scopes cannot publish.

Preserve each complete native source tree, including all requirement, rule,
version, ratio and target arrays. Local filters select whole sources, with
exact case-sensitive strings, repeated values OR and different fields AND.
Source network and status must match the same requirement and rule; target
account and network must match the same target under that rule. A source-network
filter requires a matching requirement with a child rule. Without nested filters,
sources with empty children remain visible. Children are never pruned or joined.

Blank filters reject; valid values stay unchanged, commas are not split and
asterisks are literal. Null children traverse as empty without changing output.
Unknown fields, precise numbers, null, zero and nested order remain unchanged;
roots sort lexically by native string identity. Ratio scale, timestamp units and
execution effects are not inferred from configurations. Live never publishes;
complete nonempty refresh publishes. Failed, empty or incomplete refresh preserves
the saved snapshot. No Get, execution, mutation or new Duckdog import contract.

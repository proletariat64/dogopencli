# Collection clearing system

List only: one JSON POST to `clearingNetworkInfo/pageList.json` at the verified
ifundboss API host, with pageNo1/pageSize1000. Native success, integer page echoes,
unique string IDs and native total determine completeness. The explicit empty
pageNo0 exception requires empty rows, total0 and width1000. This width is not a
measured maximum; incomplete responses never publish.

Optional local filters match whole strings exactly: repeated values OR, different
fields AND. `*` is literal; commas are not split. Blank inputs reject; accepted
values stay unchanged. Displayed records sort lexically by native string `id`.
Full native fields and nested arrays remain unchanged. No separate detail or
relationship requests are made. Live does not publish; complete nonempty refresh
publishes, and failed/empty/incomplete refresh preserves the previous snapshot.

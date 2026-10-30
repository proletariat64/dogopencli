# FX individual trades

Use one public range pair, `--from-time` / `--to-time`. Each bound accepts an ISO
calendar date or a full explicit-offset/Z instant with seconds and up to three
fractional digits. Dates expand in UTC+08 to the beginning/end of their calendar
day. Explicit instants remain exact, including an upper whole second ending in
.000. Mixed date/instant bounds and ranges across dates are supported.
Unknown offsets, naive datetimes and submillisecond input are rejected.

The leaf converts public bounds to native epoch milliseconds and SDK UTC
millisecond history bounds. Omitted IDs and bounds select yesterday in UTC+08;
planning and acquisition materialize that default before persisting it. ID-only
full inquiry remains valid, but it does not declare a bounded history range.
Original business-filter constraints are checked before default materialization.
Bare cached replay does not acquire new relative dates or apply unverified filters.

The native transaction number `uniqueId` is retained. Transport, pagination and
coverage remain the existing standard List SDK contract; business values and
nested precision are unchanged. No cross-window equivalence or merged historical
publication is declared. Old transact-from/transact-to parameter names retire.

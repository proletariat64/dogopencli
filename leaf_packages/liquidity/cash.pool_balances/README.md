# BANK cash pool balances

`dogopencli liquidity list cash.pool_balances` reads saved native pool balances.
Add `--live` for an inquiry without publication, or use
`liquidity refresh cash.pool_balances` to replace the accepted saved list.

POST JSON `/cashPoolList.json` fixes tenant `GUAPW3SG`, category `BANK` and
`pageSize=100` with zero-based `rowStart` offsets. Rows retain all native fields,
unknown fields, exact amounts and null/empty/zero distinctions.

One row represents one pool; `cashPoolMemberVOS` retains its members. Pool totals
are independent source amounts and are never recomputed from members. Native UI
pool summaries use USD; `mainCurrency` remains pool configuration. Original member
balances use `currency`; equivalent balances use `bankCurrency`. Unknown or empty
currencies remain unknown, with no conversion.

`currentBalance` is book balance; `currentAviBalance` is available for payments.
They need not agree or have a fixed ordering. Close balances refer to the previous
statement day. `valueDate` describes the pool balance date; member observation
times remain unknown and capture time is not a balance observation time.

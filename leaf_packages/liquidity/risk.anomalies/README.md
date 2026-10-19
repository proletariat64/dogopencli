# risk.anomalies

Native inquiry-only Get through the host SDK.

## Native detail

`dogopencli liquidity get risk.anomalies RECORD_ID` queries `/api/risk/event/detail.json` using native `riskEventId` and validates root `id`. the original fields, nested arrays, JSON types and exact values are retained. Separate history, logs and child endpoints are unqueried. Get never publishes cache or Duckdog data.

This package provides Get only. The List remains HOLD pending its native identity/total qualification.

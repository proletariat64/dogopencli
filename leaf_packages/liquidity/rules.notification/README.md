# Notification rules

Inspect native configuration through inquiry-only requests.

## Queries

```bash
dogopencli liquidity get rules.notification NATIVE_ID
```

## Native contract

- Fixed GUAPW3SG tenant. Native fields, nested values, exact decimals and unknown fields are retained.
- Native get sends id as a string to GET /messageNoticeConfigDetail.json; no implicit list lookup.
- Get-only; notification list remains retired. Supply a valid native configuration id from permitted UI/context; no enumeration or version guessing.

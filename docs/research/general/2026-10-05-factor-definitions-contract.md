# Liquidity pricing factor type definitions

Observed: 2026-10-05
Scope: general
Status: snapshot

Evidence scope: Asia/Shanghai, fixed Liquidity PortfolioMgmt tenant factor type
reference catalog (#105). Native inquiry contract verified before implementation;
public CLI production UAT passed for this list; see
[the sanitized report](2026-10-05-factor-definitions-uat.md).

`liquidity pricing factors list` reads GET `/getPriceEnv.json` on
`iliquidity.alipay.com` with only the existing fixed `tntInstId`. The request is
unpaginated and executes once. Both `resultFlag=true` and `result.success=true`
are required. Only `result.data.factorTypes`, an object array, supplies records.
A successful explicit empty array is complete; missing/wrong containers, business
refusal, permission/authentication and transport failures do not publish emptiness.
`reported_total` remains null; the native enumeration contract establishes
coverage without a fabricated count. The observed ten codes are not an enum or cap.

Identity is the native nonempty string `code`; labels `description` and
`englishName` remain raw, preserving missing/null/empty/unknown values.
Projection exposes only those three fields. Duplicate raw rows remain incomplete;
conflicting native content for one code hard fails before projection, including
differences in excluded fields. No translated labels, ids, business versions,
source timestamps or broader pricing environment fields are generated.

Synthetic native response shape (invented values):

```json
{"resultFlag":true,"result":{"success":true,"data":{"factorTypes":[{"code":"SYN-FACTOR","description":"合成标签","englishName":"Synthetic"}]}}}
```

This is **reference** information: type definitions identify and explain pricing
data. The existing `factor-values list` remains an independent dated runtime
inquiry at `/costFactorList.json`, with its existing fields and cache.
`factors get` remains unsupported. `/queryCostParameters.json` was used only to
cross-check native code sets and is never a fallback or second production source.

The reference snapshot profile retains one current capture per exact contract
scope. Default reads stay offline; explicit refresh atomically replaces a capture;
live neither writes nor falls back. Kind/origin/tenant/schema/projection isolate
`factor-definitions-v1` captures from old placeholders and other pricing leaves.
Capture time is not native definition update time. ADR 0016/0018/0019 retention,
safe partial/strict policy and hard failure rollback apply unchanged.

Public CLI tests use fake CDP and real temporary SQLite for exact request,
projection fidelity, future codes, malformed identity/envelope, duplicate
incompleteness, strict rollback, safe partial publication, successful empty,
disconnected reads and byte-identical live cache checks. Production UAT is
serialized with #103/#104 and must verify all native code/labels and same-capture
metadata independently before closure. Rules monitoring remains HOLD.

User authorization for local Kimi/API source-spec transfer was granted on 2026-10-05. The actual static Standards/Spec review of [source commit `fe33524`](https://github.com/proletariat64/dogopencli/commit/fe335248961838db52a0a263f10eff61abe7de1c) completed successfully with no confirmed correctness/spec defects; confidence: 4/5. Tests, lint, graph analysis and production UAT were run independently by the root coordinator, not by Kimi. This subsequent documentation-only commit is not claimed to have been re-reviewed by Kimi.

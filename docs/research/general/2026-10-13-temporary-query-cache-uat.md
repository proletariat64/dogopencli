# Temporary query cache production smoke — 2026-10-13

Observed: 2026-10-13
Scope: general
Status: snapshot

Implementation: issue #157 / PR #158. Executed the implementation from an editable
installation in an isolated `/tmp` virtual environment, dedicated Chrome
profile and CDP port 19257. The user completed SSO. Business requests used
allowlisted inquiry contracts only. All refresh/prune writes used a disposable
SQLite cache; production profiles, existing user caches and source datasets were
preserved. No private response bodies or object identifiers are included here.

| Check | Observed result | Evidence boundary |
| --- | --- | --- |
| Liquidity authentication | Authenticated, healthy, headed Chrome | Independent domain probe |
| Cash balances `--live`, no business parameters | Native entity ALIPAYGM, GMT+08 latest variant; acquired 663, reported 665; displayed 100 | `complete=false`: count shortfall and 2 duplicate arrivals; no cache created |
| Cash balances `--live --from-date 2026-10-12 --to-date 2026-10-12` | Daily native variant; acquired 710 across 30 chunks; displayed 100 | `complete=false`: dependency incomplete and count shortfall; no cache created |
| Cash refresh `--entity ANY`, one genuine account alias | Read-only DuckDB logical selector `liquidity/reference/entities`, VARCHAR instId; selected ALIPAYGM; acquired/published 1 | `complete=true`; full nonempty result replaced own temporary slot |
| Offline ANY replay, `--limit 0` | Returned same saved row and frozen selection | Selector file temporarily absent, CDP configured to an unused port; cache SHA-256 unchanged |
| Risk SLA live list then native get of a returned ID | List 49 complete records; native getter returned matching identity and `source=live` | Getter did not modify the cash cache; no cached detail or list-row substitution |
| Cash sibling prune, twice | First `pruned=true`; second `pruned=false`; later offline list `CACHE_MISS` | Disposable cache only; no browser request |
| FX authentication | Authenticated, healthy | Independent FX domain probe |
| FX trade `--live`, no ID/dates | Backend refused with `BUSINESS_QUERY_FAILED`, business code `IPAY_RS_520000500` | Previous complete GMT+08 day was 2026-10-12; production query acceptance blocked |

The broad Cash inquiries exercise the request and quality reporting contract;
they do not prove complete production datasets. The narrow ANY query and native
getter passed. No legitimate empty Cash result occurred in this bounded smoke;
empty-refresh preservation, strict rollback, legacy format discard and concurrent
publication remain local fake-CDP/SQLite acceptance evidence. FX production
acceptance remains blocked by the backend error. Local CI/review is reported
separately in the PR.

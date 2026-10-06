# Batch F gated-leaf production UAT

Observed: 2026-10-06
Scope: general
Status: passed — production gate UAT for nine deferred leaves, no enablement

## Protocol

Public CLI at commit 8368b91 (`feat/batch-F`, PR #120), user production config (`~/.config/dogopencli`), dedicated probe browser `DOGOPENCLI_CHROME_CDP_URL=http://127.0.0.1:9223` (isolated `chrome-issue88-9223` profile; headless, serial, no other pages touched). Prerequisite: `dogopencli auth check --domain liquidity` returned `authenticated: true` on that CDP before and after the run.

Every command below is a gate/discovery command on a deferred leaf; per the frozen Batch F contracts none of them may reach the transport. The production cache file `~/.local/share/dogopencli/cache.sqlite3` was hashed before and after the run: `4b9fcb7d80978224…` — byte-identical.

## Per-leaf results (39/39 PASS)

For each of the seven list leaves (`cash wallets list`, `cash wallet-balances list`, `operations rule-status list`, `investment offers list`, `investment quote-sessions list`, `investment investable-funds list`, `network routes list`):

- `list` (default offline): exit 1, `UNSUPPORTED_CAPABILITY`, message names the leaf's evidence-specific blocker.
- `list --live`: exit 2, `INVALID_ARGUMENT`; no execution.
- `refresh <leaf>`: exit 2, `INVALID_ARGUMENT`; no execution, no cache write.
- `help` / `describe`: exit 0, deferred status and reason surfaced.

Plus `cash wallets get` and `network routes get`: exit 1, `UNSUPPORTED_CAPABILITY`; `snapshot liquidity --format json`: exit 0, all nine F1–F4 leaf nodes `availability: unsupported`, `cache.status: not_applicable`, reasons matching `leaves.py` verbatim; `describe liquidity cash wallets`: exit 0.

## Outcome

- All nine Batch F terminal leaves remain non-executing in production with named, evidence-specific blockers; discovery surfaces help/describe/snapshot uniformly.
- No backend request beyond the auth-probe navigation occurred during the UAT; the dedicated liquidity application session on CDP 9223 remains valid.
- This validates the deferred-gate behavior of PR #120 only. It does not and cannot validate list delivery: every leaf stays unsupported pending positive native evidence (wallet membership mapping, independent wallet-balance caller, populated investable-funds ranges, native offers/sessions/route-list callers). Per-leaf production CLI UAT of actual list delivery remains gated on those future enablements, per issues #116–#119 and parent #72.

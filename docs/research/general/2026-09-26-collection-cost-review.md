# Collection cost PR review validation

Observed: 2026-09-26
Scope: general
Status: snapshot

Validated the user-supplied Kimi review of commit `43da76a` and the
[GitHub review](https://github.com/proletariat64/dogopencli/pull/22#discussion_r4107646787).
Read the inline review, review summary, PR body and issue #21. No production
queries or business writes were needed for this repair.

## Findings and decisions

| Finding | Validation and resolution |
| --- | --- |
| AGENTS excludes collection | Valid stale standard. Updated current scope to payment plus issue #21 collection costs; preserved all collection deferrals and inquiry-only restrictions. Removed obsolete pre-scaffolding claims. |
| Documentation tree/payment-only spec | Valid. Updated plugin tree and current scope; retained v0.1.0 as historical payment-only scope. |
| Missing collection vocabulary | Valid. Added collection transaction-cost configuration to CONTEXT, distinguished from actual fees and VA fees. |
| Payment-only package descriptions | Valid. Updated both package metadata and module description. |
| Bundled browser fixes / launcher scope creep | Packaging concern, not a missing feature or reason to remove required fixes. Ownership repair was needed to restore the dedicated browser during this work; target readiness fixed a reproduced UAT failure. Keep both, document their purpose, and deliver review repairs in a separate follow-up commit without rewriting published history. |
| Collection inherits payment behavior | Valid coupling concern. Independent capabilities now call shared cost parsing and sorting functions and share table columns; collection cannot inherit payment filters or pagination policy. |
| Refresh hint string surgery / suffix assumption | Valid maintenance concern. Command handlers supply explicit refresh commands to the shared CLI helper. No capability-name parsing remains. |
| Private readiness helper import | Valid boundary concern. Exposed await_target_settled publicly and updated callers without changing its behavior. |
| v0.1.4 contradicts old issue wording | Stale issue status, not an unauthorized version bump: the user subsequently requested a PR and patch-version increment/tag. Retain 0.1.4 and synchronize issue status. Historical v0.1.0 ADR and payment UAT issues remain unchanged. |
| Lockfile growth without manifest changes | Verified manifest/lock drift repair: origin/master already declares jsonschema>=4.18 in the dev extra. Added lock entries are that existing dependency and its transitive requirements. Offline uv lock --check passes. |
| Shared readiness affects payment | Valid regression concern. Run the blank/loading readiness and SSO/foreign-origin rejection scenarios against both payment and collection capabilities, plus the existing payment CLI and full suite. |
| Flattened profile paths split at spaces | Confirmed by failing tests for spaces and apostrophes. Chrome's process title is space-joined argv, not shell syntax. Split at switch boundaries, preserve literal value text, reject non-exact profile values and multiple profile switches. NUL-delimited argv remains unchanged. |

## Verification and release boundary

Regression tests first reproduced two launcher failures. The repaired tests cover
NUL-delimited and flattened argv with ordinary paths, spaces and apostrophes,
actual-listener selection, foreign/multiple owners, and profile-prefix rejection.
Readiness tests now cover both payment and collection explicitly.

The previously published v0.1.4 tag still points to `43da76a`; these review fixes
advance the PR branch only. The tag is not moved, and the PR is not merged.
The earlier 84-case production UAT is historical evidence for the feature, not a
claim that live UAT was repeated for this repair.

Final checks: full suite 583 passed and 23 subtests passed; focused payment,
collection and readiness run 116 passed. After adding two duplicate-profile
rejection cases, all 25 launcher tests passed. Ruff check and format check,
doc-guard (32 Markdown files), offline lockfile validation and git diff whitespace
checks passed. Graph refreshed and changes analyzed against origin/master;
its static test-gap suggestions were checked against the executable tests above.

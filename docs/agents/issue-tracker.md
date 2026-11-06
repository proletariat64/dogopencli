# Issue Tracker: AntCode

Issues and specs live in AntCode project `pd.pt/dogopencli`.
Use `rtk antcode`; the project is inferred from the current `origin` remote.

## Operations

- Read: `rtk antcode issue show <issue-iid> --json`
- List: `rtk antcode issue list --state opened --limit 100 --json`
- Create: `rtk antcode issue create --title "feat: ..." --description "..."`
- Comment: `rtk antcode issue note create <issue-iid> "..."`
- Replace labels: `rtk antcode issue update <issue-iid> --labels "needs-triage"`
- Close: `rtk antcode issue close <issue-iid>`

Use conventional title prefixes. Read an issue and its notes before acting on it.
Map triage roles using `triage-labels.md`.

`issue update --labels` replaces the complete label list. Include every label
that must remain; do not treat it as an append operation.

## Skill terminology

“Publish to the issue tracker” means create an AntCode issue.
“Fetch the relevant ticket” means read the AntCode issue and its notes.

## Pull requests and validation

PRs as a request surface: no.

AntCode PR creation, default `--no-review-required`, and merging follow the
repository root `AGENTS.md`; this file does not duplicate those commands.

No hosted CI pipeline is configured. Run the required local pytest and Ruff
checks documented in the root `AGENTS.md` before creating or merging a PR.

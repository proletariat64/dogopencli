# Issue Tracker: GitHub

Issues and specs live in `proletariat64/dogopencli`.
Use the `gh` CLI, prefixed with `rtk proxy`.

## Operations

- Read: `rtk proxy gh issue view <number> --repo proletariat64/dogopencli --comments`
- List: `rtk proxy gh issue list --repo proletariat64/dogopencli --state open --json number,title,labels`
- Create: `rtk proxy gh issue create --repo proletariat64/dogopencli --title "feat: ..." --body-file <path>`
- Comment: `rtk proxy gh issue comment <number> --repo proletariat64/dogopencli --body-file <path>`
- Label: `rtk proxy gh issue edit <number> --repo proletariat64/dogopencli --add-label "<label>"`
- Close: `rtk proxy gh issue close <number> --repo proletariat64/dogopencli`

Use conventional title prefixes. For multiline bodies,
write the exact Markdown to a temporary file and use
`--body-file`. Map triage roles using `triage-labels.md`.

## Skill terminology

“Publish to the issue tracker” means create a GitHub issue.
“Fetch the relevant ticket” means read the issue and its comments.

## Pull requests as a triage surface

PRs as a request surface: no.

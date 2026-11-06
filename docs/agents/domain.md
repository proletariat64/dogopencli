# Domain Docs

## Before exploring

- Read the root `GLOSSARY.md` and the current guide responsible for the task.
- Read relevant ADRs under `docs/adr/` when that directory exists.
- For leaf work, read `tools/leaf-dev/handbook.md`; for domain/authentication
  contracts, read `docs/agents/domain-components.md` when relevant.

Missing optional ADR files do not block exploration. Create them only when a
decision needs to be recorded.

## Layout and maintenance

This is a single-context repository: one root `GLOSSARY.md` and optional
`docs/adr/`.

Maintain business terms in `GLOSSARY.md`. Keep current behavior in the single
guide responsible for it, and use the glossary's defined vocabulary in issues,
specs, design proposals and tests. Surface any conflict with an existing ADR.

Requirements, acceptance scope and task status belong to the assigned AntCode
issue. Current documents do not accumulate execution logs, version history,
old UAT journals or historical specification copies.

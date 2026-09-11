# Domain Docs

## Layout

Use a single context:

- `CONTEXT.md`: repository-level domain vocabulary.
- `docs/adr/NNNN-<decision-slug>.md`: architecture decisions.

## Before exploration

Read `CONTEXT.md` and ADRs relevant to the work.
If they do not exist, proceed silently. Create domain
documents through domain-modeling when terminology or
decisions are resolved, rather than adding empty placeholders.

## Vocabulary

Use terms defined in `CONTEXT.md` in issues, designs,
code, and tests. Respect explicitly discouraged synonyms.
Record unresolved terminology gaps for domain-modeling.

## Decision conflicts

Identify any proposal that contradicts an existing ADR.
Reference the ADR and explain why reconsideration is needed;
do not silently override it.

---
name: code-review
description: Review a PR diff once and report concrete correctness findings.
---

Review the supplied Git diff and read only the relevant source and local documentation.
Perform the review yourself; do not delegate, start background tasks, or wait for notifications.
Do not execute tests, lint, installation, network requests, or business operations. Ruff runs in the separate CI workflow.
Do not modify files, commit, push, or read credentials or user configuration.
The GitHub runner has no rtk or code-review-graph; use direct Git and file inspection commands.
Report Standards and Spec briefly, citing file, line, severity and evidence for actionable correctness findings.
If no local spec is available, state that limitation. If no findings exist, say so.
Return a concise Markdown review with exactly one overall confidence: ?/5 and its rationale.
State that tests, graph analysis and production UAT were not run. Do not claim CI passed.

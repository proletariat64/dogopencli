# Domain identity and authentication

A domain represents a business area. Payment and collection remain separate
domains even when their entry URLs are equal. Built-in domain metadata belongs
to [domain_contracts.py](../../src/dogopencli/domain_contracts.py); installed
manifests own business leaf declarations. Domain discovery never imports business
adapters or initializes a legacy registry.

## Contract and ownership

`DomainDeclaration` contains only `id`, the verified HTTPS `entry_point`, and
`DomainAuthPolicy`. `domain_declarations()` returns the ordered static declarations.
There is no domain package installer, mutable business registration API, handler
mapping, refresh order or domain-owned cache-name lookup.

The host owns domain enablement and observations, the dedicated browser profile,
shared OAuth lifecycle, inquiry transport, result policy, cache and rendering.
Installed leaf packages own their native contracts, request construction,
parsing, supported filters and any specialized collection policy. Use the
[leaf handbook](leaf-plugins.md) for new inquiries.

`DomainAuthPolicy` declares whether login preserves an existing headed browser,
uses document completion, and performs bounded handoff. FX and liquidity require
those policies. An optional domain-specific probe uses the existing shared browser
primitives: it accepts a `BrowserEnvironment` and keyword-only `timeout`, returns
shared authenticated verdict including browser `mode`, and raises `AuthError`
for failures. It must not start another browser, extract cookies or bypass request
restrictions. A shared portal or OAuth session never proves another domain's access.

Domain metadata imports are side-effect-free. Adding a domain requires verified
entry/auth behavior and a static declaration, not a branch in business dispatch.
Removing a declaration must not clear configuration, caches, datasets or browser
authentication. New business behavior is delivered through an installed leaf.

## Settings and observations

The shared domain service supplies inventory and enable/disable to CLI and GUI.
It uses the effective configuration scope. Inventory reads do not create a store
or probe applications. Domains default to enabled unless a persisted override
exists. Installed manifests and discovery diagnostics determine leaf inventory;
there is no separate per-leaf enable switch.

Business execution checks domain enablement before cache or browser access.
Disabling a domain preserves its installed leaves, cached data and historical
outcomes. Already-started queries finish; subsequent executions see the change.
Help and describe remain offline and available without adapter activation.

Actual list, get and refresh execution records the explicit installed leaf identity,
operation, outcome, UTC time, optional error code and sanitized diagnostic.
Success and warning exit zero; failure exits nonzero. A warning reflects structured
leaf evidence, not terminal-text matching or a new domain-layer judgment.
Help, describe, inventory, prune and pre-execution rejection do not record an
execution. Never persist credentials or business payloads in observations.

Domain authentication observations are separate. Explicit login and auth checks
update them; a cached list does not prove current authentication. Observation-save
failure remains visible without changing the inquiry result. A setting change
succeeds only after durable persistence. Auth persistence warnings remain visible
with `--quiet`; output schemas and verdict exit codes remain unchanged.

Logout invalidates recorded authentication before cookie clearing. A pre-clearing
browser or lock failure preserves the prior observation. Auth check holds shared
browser control through verification and observation persistence; login/logout
hold exclusive control. Auth checks may create local coordination files but never
launch or switch Chrome.

## Local controls and GUI

Use `dogopencli domain list`, `domain show <id>`, `domain leaves <id>`,
`domain enable <id>` and `domain disable <id>`. These commands and
`dogopencli gui --config-dir <directory>` share state. The GUI displays domains,
recorded authentication, installed leaf inventory and manifest documentation forms.
It can toggle domains and edit allowed documentation prose; technical declarations
remain locked. It performs no login, business inquiry or background probe.

The GUI binds `127.0.0.1`, prints its URL and runs in the foreground. Its default
port is automatic; `--port` selects an explicit local port. Ctrl+C stops the server.
Local Host/Origin validation and a page token protect writes. Failed saves must
remain visible, without claiming a setting changed.

## Verification

Use public CLI and GUI/HTTP interfaces with task-isolated configuration and fake
external transport. Cover offline discovery, current help, disabled-domain
rejection, authentication selection, persisted outcomes, failed saves and retained
cache/Duckdog ownership. The installed-artifact gate must exercise those paths
without retired business modules or source-checkout imports.

Production auth and UAT remain separate acceptance layers. Read the repository
browser instructions first; use the task-owned profile and an allowed CDP port,
manual SSO, verified inquiry contracts and private raw evidence. No synthetic test
establishes production access.

# Domain identity, authentication and operational state

Status: accepted domain foundation; business registration superseded by
[ADR 0022](0022-installed-leaf-pilots.md) and
[spec #255](https://github.com/proletariat64/dogopencli/issues/255).
Date: 2026-10-16

## Context

[Issue #200](https://github.com/proletariat64/dogopencli/issues/200) established
payment, collection, FX and liquidity as peer domains with shared browser/auth,
local controls and operational observations. Installed leaf packages subsequently
became the owner of business discovery and execution. Retaining old domain leaf
registration would load a second business runtime even for neutral host imports.

## Decision

Domains represent business concepts, not portal URLs. Payment and collection
remain distinct despite sharing an entry portal. Static, side-effect-free
`DomainDeclaration` values contain identity, verified entry URL and
`DomainAuthPolicy`; `domain_declarations()` provides the ordered set. The host
owns browser profile/lifecycle, shared OAuth/SSO, transport restrictions,
authentication recovery, local state and generic result policy.

Installed manifests provide dotted leaf identities, supported operations, help,
descriptions and dataset bindings. Adapters provide native business behavior.
Domain metadata contains no leaf implementation, registry, dispatch handler,
command group, refresh order, business parser or cache-name lookup. Neutral
transport/result protocols have their own `dogopencli.contracts` owner.

The original transitional business-registry assembly is retired, including its
compatibility paths. Required domain/auth metadata moves to the clean declaration
contract. Historical source is available only through isolated pinned release
references; it is not shipped in the repository or new distributions.

## State and execution

Disabled domains remain discoverable, reject business execution before cache or
browser access, and are omitted from default login/auth checks. Explicit login
for a disabled domain fails without enabling it. Disabling preserves installed
leaves, cached data and recorded outcomes; already-started queries finish.
There is no independent per-leaf enable switch.

Actual installed-leaf list/get/refresh execution records its explicit global
identity, operation, outcome, UTC time and sanitized diagnostic. Initial outcome
is `unknown`; success and warning exit zero, failure exits nonzero with an error
code. Warning reflects the leaf's structured caveat. Help, describe, inventory,
prune and rejection before execution do not create an execution observation.
No heartbeat, background polling, credentials or business payloads are stored.

Domain authentication observations are separate. Only explicit login/auth checks
refresh verified status and time; cached replay does not prove authentication.
Metadata is held in a versioned SQLite store adjacent to effective configuration.
Absent-store reads are nonmutating; writes are transactional and corrupt state
fails explicitly. Observation-save errors remain visible without changing the
business result; setting changes succeed only after durable persistence.

## Shared login

Bare `dogopencli login` selects all enabled domains. Repeatable `--domain`
selectors choose a subset. Shared portal/session establishment may be reused,
but every selected domain receives its own verified verdict. Overall exit is
nonzero if any selected domain fails.

Keep the headed human SSO and verified headless handoff. Domain authentication
policy controls quiet document completion and bounded handoff where required;
successful OAuth alone is not proof of application access. Shared control locks
prevent login/logout races with checks and active inquiries. Logout invalidates
recorded authentication before clearing cookies, while pre-clearing browser/lock
failure preserves prior observations.

## CLI and localhost GUI

`domain list`, `show`, `leaves`, `enable` and `disable` share one service with
the GUI. Inventory reads recorded observations without probing production.
`dogopencli gui` binds loopback, prints its URL, runs in the foreground and stops
on Ctrl+C. It displays domains and installed leaves, toggles domains and edits
permitted manifest documentation. Technical identity and operation declarations
remain locked. Host/Origin checks and page tokens protect local writes.
There are no GUI login, business-query, import or package-management actions.

## Acceptance

Preserve public domain/auth, current help/GUI, explicit installed-leaf execution
observations, cache and Duckdog ownership through the retirement. Verify public
CLI and GUI/HTTP behavior with isolated configuration and controlled transport.
Combine static dependency checks with fresh installed positive execution outside
the checkout. Production UAT remains a separate gate; details and evidence belong
to [spec #255](https://github.com/proletariat64/dogopencli/issues/255) and the
[leaf evidence companion](../agents/leaf-handbook-evidence.md).

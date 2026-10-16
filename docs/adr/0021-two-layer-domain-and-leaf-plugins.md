# Two-layer domain and leaf plugins

Status: accepted; implementation specified in issue #200
Date: 2026-10-16

Planning map: [Chart the domain component rebuild](https://github.com/proletariat64/dogopencli/issues/196).
Implementation contract: [Rebuild the domain component layer](https://github.com/proletariat64/dogopencli/issues/200).
The map's child decision tickets provide the supporting design decisions.

Rebuild payment, collection, FX and liquidity as standard domain components
above the existing leaf capability registry. Each domain owns its identity,
entry point, enabled state, authentication status and registered leaf inventory.
Shared core validates and assembles them through one uniform interface. This makes the peer-domain model
in [ADR 0015](0015-peer-domain-plugins-and-shared-auth.md) concrete without
replacing the leaf contracts established under
[ADR 0001](0001-query-capability-model.md).

## Context

Leaves already register capabilities, commands, refresh commands, groups,
descriptions and collection callbacks through `plugins.register()`. Domains
still require special wiring in shared code:

- `plugins._load_builtins()` imports individual leaves and handles liquidity
  retired/deferred leaves and collection refresh ordering explicitly.
- `catalog._GROUPS` declares domain navigation. Catalog assembly also constructs
  payment and FX refresh commands and selects liquidity prune commands by leaf
  name.
- Catalog normalization and discovery recognize the domain-specific handler
  name `cmd_liquidity_unsupported`.

Some leaves already declare groups locally, but no common domain interface
owns the complete contribution. Adding or removing a domain therefore requires
coordinated changes outside its package.

## Decision

Domains represent business concepts, not portal URLs. Payment and collection
remain distinct even when they share an entry portal. Each domain declares its
own entry point and authentication check. The browser profile, shared OAuth/SSO
session and browser lifecycle belong to the CLI core, never to a domain.

Build a component layer first, within the existing distribution. Static
registration is sufficient; separate domain packages, package-management
commands and hot loading/unloading are outside this effort. Use
registered/unregistered to describe component membership.

A domain module supplies a `DomainComponent` implementing the `DomainPlugin`
protocol as its complete declaration. A leaf remains the query capability
and its command metadata within that declaration. Keep `Capability`,
`EndpointContract`, collectors and existing query implementations unless a
specific compatibility requirement needs a change.

The declaration contains domain identity, root and navigation groups, leaf
registrations, descriptions, and application/auth metadata required by
ADR 0015. Prefer declarative data over callbacks that mutate shared registries.
`DomainAuthPolicy` declares application auth behavior and an optional probe;
`LeafRegistration` binds each capability to its operations and contributions.
These declarations do not require a class hierarchy or a separate method for
every field.

Every domain must answer the same five questions within its own package:

1. What is its root command?
2. What groups and navigation order does it expose?
3. Which leaves are registered, and what are their enabled states and last
   recorded execution results?
4. What refresh tree does it expose, including execution bindings and order?
5. Which leaves own temporary query caches, and what prune paths apply?

Internal capabilities may be registered without public commands. Group nodes
may also be executable, as with existing collection refresh commands. Query
and refresh ordering must be explicit where they differ; neither depends on
reserved empty entries in another domain's registry.

Registered leaves expose only enabled/disabled state. Previously gated or
retired entries become disabled entries, without a reason field in this model.
Unregistered leaves disappear from inventory. Registration and enabled state
do not prove production UAT, authorization or a successful execution. This
change does not supply implementations for currently unsupported inquiries.

Derive cache operations from explicit cache ownership and supported operation
metadata. A command suffix or handler name alone does not establish cache
ownership. Preserve existing prune paths, including declared legacy paths,
without a core list of liquidity leaf names. Online detail inquiries do not
acquire cache ownership merely because they share a domain with list inquiries.

Shared core continues to own transport restrictions, browser lifecycle,
authentication recovery, cache mechanisms, output and generic catalog
validation. Domain-supplied origins and auth probe contracts use those shared
mechanisms; plugins cannot bypass request allowlists or install an independent
login stack. One domain's authentication never proves another's access.

## State and execution

Disabled domains remain discoverable, block business execution and are skipped
by default login/authentication checks. Disabling a domain preserves cached
data and individual leaf settings. Re-enabling it restores the effective state
of those leaves. An explicit login targeting a disabled domain fails clearly
without enabling it.

Each registered leaf has a persisted last execution result: `unknown`,
`success`, `failed` or `warning`, with operation name, update time and a brief
diagnostic where applicable. Initially the result is `unknown` with no execution
timestamp. `success` and `warning` exit 0; `failed` exits nonzero and carries an
error code. A warning reflects a completed execution with a reported caveat,
such as a usable incomplete result; the domain layer records the leaf outcome
without adding new business judgments.

Only actual leaf execution updates this result. List, `get` and refresh use the
status of their registered leaf; distinct registered leaves keep distinct
results. Help, describe, inventory and prune do not update execution results.
There is no heartbeat, periodic leaf polling or explicit leaf health probe.
Persist metadata across CLI invocations without business payloads or credentials.

Domain authentication status is separate: retain the last verified result and
its timestamp, updated by login/auth check. Inventory displays recorded status
without probing the network or interpreting old evidence as current health.

## Login orchestration

Bare `dogopencli login` targets all enabled domains. Use the default domain
entry portal to establish shared OAuth/SSO, then establish and verify the
remaining domain sessions through their declared interfaces as needed. Shared
portal URLs may reuse session establishment, but each domain retains its own
authentication verdict.

Use repeatable selectors for a subset:

```bash
dogopencli login --domain payment --domain collection
```

Report every selected domain's outcome. Overall exit is nonzero if any selected
domain fails. Preserve the shared headed human SSO and headless verification
lifecycle; successful OAuth alone is not successful authentication for all
domains. These multi-domain semantics intentionally extend ADR 0015.

## CLI and localhost GUI

Provide `domain list`, `domain show <domain>`, `domain leaves <domain>`,
`domain enable <domain>` and `domain disable <domain>`. Results use the shared
structured envelope, with text output available. Inventory is offline and
domain settings and recorded results are shared by CLI and GUI through one
domain service. A versioned SQLite store adjacent to the effective config file
holds operational metadata separately from business caches. Absent-store reads
return defaults without creating a file; writes are transactional and corrupt
state fails explicitly rather than silently enabling domains.

`dogopencli gui` starts a foreground localhost web server, prints its URL and
stops on Ctrl+C. Version 1 shows domain status and enables/disables domains.
Leaves appear only as a read-only list under their domain. There are no leaf
controls, login actions or business-query execution in the GUI.

Changes apply to subsequent executions. Queries already running finish under
the settings with which they started. The GUI does not introduce background
authentication checks or leaf probes. The server binds loopback, chooses an
available port by default, and serves bundled assets. Reads use
`GET /api/domains`; domain toggles use `POST /api/domains/<domain>` with an enabled
boolean. Mutations require the local page token and matching Host/Origin;
state-changing GET requests are unavailable.

## Registration and lifecycle

Use a static, ordered list of built-in domain module paths. Core imports each
through the same interface; it does not import individual leaves. Adding a
domain changes this list and adds its package, without adding domain branches
to catalog or transport code. Entry-point discovery and external plugin
installation remain deferred: deterministic offline startup meets this
single-machine CLI's needs.

`register_domains()` validates the complete contribution set before publishing it.
Validate unique domain and capability identities, command-path collisions,
domain ownership of query paths and corresponding refresh/prune subtrees,
parent reachability, and executable handler bindings. Handler existence must
be checked at a composition point where bindings are available; identifier
syntax alone is insufficient. Retain `build_catalog()` invariants, including
derived children and reserved authentication paths. A failed registration must
not leave partial entries in any registry.

Removing a domain from the built-in list removes its capabilities, navigation,
descriptions and generated refresh/prune operations together. Other domains
must still build and operate. This is registration atomicity, not a runtime
uninstall operation: it does not delete persisted caches, configuration,
profiles or credentials. Existing cache files are never discovered as active
leaves solely because they remain on disk.

## Migration and acceptance

Migrate in order: payment, collection, FX, then liquidity. Establish the shared
interface with payment, then use each subsequent domain to verify the same
seam handles its existing behavior. Temporary legacy assembly may serve
unmigrated domains, but each domain must have exactly one active owner and the
legacy assembly must disappear when migration finishes.

Preserve existing query command paths, ordering, options, output envelopes,
cache identities and inquiry contracts except for the explicitly agreed
enabled-state representation and execution gating. Multi-domain login and the
new management interfaces are deliberate behavior additions. Preserve current cache semantics under
[ADR 0020](0020-temporary-query-cache-and-duckdog.md).

Acceptance must demonstrate:

- Each built-in domain supplies the same declaration interface and owns answers
  to all five questions. Shared catalog assembly contains no domain-name,
  leaf-name or domain-handler branches.
- Omitting any one domain contribution removes its whole command and capability
  contribution while leaving the others valid.
- Invalid or conflicting declarations fail without partially changing the
  registry; missing parents and handlers fail clearly.
- Public CLI checks preserve query, help, description, refresh and prune
  behavior, including distinct refresh order, executable parents, internal
  capabilities, disabled entries and uncached detail inquiries.
- Offline discovery requires no browser or business network access. Fake-CDP
  checks preserve allowlists, authentication failures and domain-specific
  inquiry contracts. Production UAT is recorded separately from local checks.
- Disabled domains retain their leaf settings and caches; re-enabling does not
  fabricate successful auth or execution observations.
- Login reports all selected outcomes and fails overall on any selected failure.
- GUI version 1 controls domains only; leaf inventory is read-only. CLI and GUI
  observe the same persisted settings and execution/authentication records.
- A new-domain development guide and working sample demonstrate identity,
  entry/auth integration, leaf registration, state reporting and removal through
  the same interface used by all four built-in domains.

Keeping the current leaf-only arrangement would avoid migration work but leave
domain knowledge scattered in core. Replacing the leaf layer would expand the
change without resolving that ownership problem. The additional domain seam
costs declaration and validation code, but concentrates domain wiring in one
place and makes domain removal testable through the same interface as startup.

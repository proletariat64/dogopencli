# Building a domain component

A domain represents a business area. Payment and collection are separate
domains even though their entry URLs are equal. The CLI distribution contains
the domain components; this interface does not require separate packages or
runtime installation.

## Contract and ownership

Implement the domain protocol with a `DomainComponent`. Declare a stable ID,
HTTPS application entry point, authentication policy, ordered navigation groups,
leaf registrations and optional refresh order. Keep identifiers stable across
releases because settings and observations use them as identities.

Core owns the browser profile, shared OAuth lifecycle, approved transport,
catalog assembly, execution policy, persistence and rendering. A domain declares
its application-specific probe through `DomainAuthPolicy`; reuse the existing
shared browser primitives. Never start a separate browser, extract cookies or
send unrestricted requests from a domain adapter. Sharing an entry URL does not
share a domain auth verdict.

Each `LeafRegistration` declares its capability, enabled default, command nodes,
refresh nodes, descriptions and any collector or refresh hint. Use
`leaf_registration` for the existing capability conventions. Its operation
metadata binds public list/get/refresh operations to one stable leaf ID. A get
capability registered separately retains its own execution observation. Do not
merge list and get by matching their names or paths.

Reuse a supported shared query handler and its capability protocol when exposing
a production command. Declaring a handler name does not implement that handler.
For a new operation implementation, declare its callback in the component's
`handlers` mapping. Core resolves it through `handler_for`; adding a domain does
not require a new branch in the core dispatcher. Handler names must not collide
with another component's binding or override reserved core handlers.
Descriptions and navigation are offline declarations; they must not open Chrome
or inspect production data.

## Registration and removal

Add the component to the ordered static registration set. Validate and publish
complete sets with `register_domains`; assemble projections with
`build_domain_catalog`. No domain-specific branch belongs in core catalog
assembly. Registration rejects duplicate identities and paths, reserved command
roots, missing parents, invalid ownership, missing execution bindings and
inconsistent cache ownership before publishing a replacement registry.

Query paths belong under the domain ID. Shared refresh, describe and prune
projections retain the same domain and leaf owner. Declare executable parents
explicitly; child lists are derived. Declare refresh order when it differs from
query order.

Remove a component by omitting it from the next registration set. Its inventory,
auth selection and catalog contributions disappear together. Registration
changes take effect on the next CLI invocation; GUI registration is loaded at
startup. Removal preserves local state and query caches. Re-registering the same
identity can reuse those records, whose timestamps remain visible.

## Settings and observations

The shared domain service provides inventory and enable/disable to both CLI and
GUI. It resolves the same effective configuration scope as other commands.
Inventory reads do not create a store or probe applications. Domains default to
enabled unless a persisted override exists; disabled leaves keep their own
declaration or persisted setting. Unsupported registrations remain disabled.

Business execution requires both domain and leaf enabled. Check that policy
before cache access, browser work or handler invocation. Disabling a domain
preserves leaf settings, cached data and historical outcomes. Already-started
queries finish; subsequent executions see the change.

Record only actual completed leaf execution. Success and warning exit 0; failure
exits nonzero with a stable error code. A warning represents a structured caveat
already reported by the leaf, not terminal-text matching or a new judgment by
the domain layer. Persist only outcome, operation, UTC update time, optional
error code and a brief sanitized diagnostic. Never persist credentials or
business payloads in operational observations. Initial outcome is `unknown`
with no execution time.

Help, describe, inventory, prune and invocations rejected before entering a leaf
handler do not update execution observations. Domain auth observations are
separate and updated by explicit login/auth checks. A cached query does not
prove current authentication. Observation-save failure must be visible without
changing the business result; a setting change succeeds only after durable save.

Cache ownership stays with existing leaves. The domain interface does not
change query cache retention or make get/live calls publish caches. Declare
cache bindings and prune projections explicitly so removal does not leave
orphan command wiring.

## Local controls

Use `dogopencli domain list`, `domain show <id>`, `domain leaves <id>`,
`domain enable <id>` and `domain disable <id>`. These commands and
`dogopencli gui --config-dir <directory>` share state. GUI v1 displays domains,
recorded auth observations and read-only leaf inventory. Its only mutation is
domain enable/disable. It performs no login, business query or background probe.

The GUI binds `127.0.0.1`, prints its URL and runs in the foreground. The default
port is selected automatically; `--port` selects an explicit local port. Ctrl+C
stops the server. It uses bundled assets, validates local Host/Origin headers,
requires a page token for writes and reports failed saves without claiming the
setting changed.

## Runnable synthetic sample

Run from the repository root:

```bash
PYTHONPATH=src python examples/domain_component.py
```

The sample registers two synthetic domains with a shared example URL, assembles
their catalogs, obtains independent fake auth verdicts and queries fake records.
It removes one domain and proves that the peer remains. It restores the original
registry before returning. It never contacts production, opens Chrome or writes
user settings. The component declares its execution callback through the same
`handlers` mapping that core dispatch uses. The demonstration resolves and runs
that registered callback with synthetic input. The sample remains outside the
production registration set.

## Verification

Test observable behavior through public CLI and GUI/HTTP interfaces using
temporary configuration and fake external transport. Prove registration
addition/removal and invalid-contribution rejection at the registration boundary.
Exercise disabled-state rejection, preserved cache bytes and leaf settings,
persisted outcomes, failed saves, auth identity and CLI/GUI read-after-write.

Run the runnable sample, focused tests, repository pytest, Ruff checks and
documentation guards. Real auth/UAT is a separate acceptance layer: use only
the task-owned profile and permitted CDP port, approved inquiry contracts and
private raw evidence. Fake transport success does not prove production access.

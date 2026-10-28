# Agent plugin development guide

## Discover before building

1. Read `api/catalog` and search existing identities, summaries and manifests.
2. Read `reference/tools/leaf-dev/README.md`, `handbook.md` and `interfaces.md`.
3. Confirm bounded business scope, native endpoint, identity, pagination and date semantics against current source evidence. Historical documents do not establish current access or behavior.
4. Get human confirmation of simple/complex scope and spec/sample before implementing new business leaves, as required by the handbook.

## Implement against the current host

Work inside a dogopencli checkout. A package contains a root `leaf.json`, the declared root Python adapter and ordinary resources. Use the runnable examples in `reference/tools/leaf-dev/example/`, `example-get-only/`, `example-single-response/` and `example-sources/`.

Use the shared List/Get SDK and neutral contracts. Keep inquiry allowlists explicit; HTTP POST alone does not imply mutation or inquiry. Preserve native fields, types and unknown values. The host owns authentication, transport, pagination conventions, completeness, cache publication, diagnostics and process exits. Help and static verification must not import adapters or create browser/network state. Never ship credentials, cookies, profiles, business data or caches.

## Validate and pack

Run from the current dogopencli repository, with its configured Python environment:

```bash
rtk proxy uv run python tools/leaf-dev/leaf.py verify /path/to/plugin
rtk proxy uv run python tools/leaf-dev/leaf.py pack /path/to/plugin --output /tmp/new-delivery
```

The pack destination must be new. Its delivery.json and SHA256SUMS describe the ZIP. ZIP root must have leaf.json directly, without a wrapper directory. Static verification does not prove runtime or production behavior. Install the exact ZIP in an isolated host configuration, run fake-response tests and authorized inquiry-only production UAT separately. Domain login belongs to the host, not this registry.

## Publish

Choose a new registry version label (1–64 ASCII letters/digits/dot/underscore/hyphen, starting with a letter/digit). It is separate from the manifest: do not add unsupported version fields to leaf.json. Publish via the website or PUT raw ZIP bytes to `api/releases/<version>` with `Authorization: Bearer <publisher token>`. Keep credentials in session memory and never put them in URLs, logs, committed files or shell history. HTTP publication requires a trusted network or protected tunnel; use HTTPS when available.

Successful publication returns HTTP 201 and the canonical metadata/download path. Existing identity + version returns 409 and cannot be replaced. The server runs the authoritative host static validator, never the uploaded adapter. The registry labels this `static-only`; the publisher must retain separate UAT evidence.

## Install and inspect

Read `api/catalog`, resolve a download path against the site's origin, download the exact ZIP and compare its SHA256 with the returned record if checking transfer integrity. This is not a signature or publisher trust proof. Install only trusted code:

```bash
dogopencli plugins install <absolute ZIP URL>
dogopencli plugins list --format text
```

Search the catalog before making a new leaf. Do not call business query APIs to test the registry.

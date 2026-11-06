# Release and publication

CLI releases, registry deployments and plugin publications are independent.
They do not perform business queries, login, data migrations or production UAT.

## CLI release

Merge source and version changes on GitHub first. Keep `pyproject.toml` and
`src/dogopencli/__init__.py` at the same version. From clean, attached `master`
matching the freshly fetched GitHub branch:

```bash
make release DRY_RUN=1
make release TARGET=antcode
make release TARGET=github
```

AntCode is the default and uses the local `antcode` CLI login. Its default artifact
project is `pd.pt/dogopencli`; set `ANTCODE_PROJECT=namespace/project` for the actual
provisioned repository. GitHub uses `gh` and publishes to
`proletariat64/dogopencli`. Authenticate the selected CLI before releasing.
AntCode project existence and publishing permissions must be provisioned on the
release host; the script does not create repositories or credentials.

The command checks source identity, runs `make check`, builds wheel/source archives,
and runs an isolated install/update/uninstall smoke test that asserts the installed
CLI reports the planned release version before creating and
pushing an annotated source tag. Only a tag is pushed, never a source branch.
Each provider receives a draft Release with the wheel, sdist, version-bound
`install.sh`, `SHA256SUMS` and `RELEASE_NOTES.md`. Publication finalizes only after
downloading and comparing every newly uploaded asset. AntCode's declared default
branch revision is an artifact-host carrier; the notes record the actual GitHub
source commit and tag.

For retry or publication of the same source version to the second provider:

```bash
make release TARGET=github RETRY=1
make release TARGET=antcode RETRY=1
```

Existing tags must resolve to HEAD. Existing same-source packages remain canonical
and are downloaded for checksums; no attachment is overwritten. Completed matching
Releases are no-ops. For publication of already-built artifacts only:

```bash
make publish-release TARGET=github TAG=v0.6.4 DIST_DIR=dist
```

Use a clean `DIST_DIR` for a new version. Release tools do not increment versions.
`DEV_PYTHON` defaults to `.venv/bin/python` and requires Python 3.12+;
`uv sync --extra dev --inexact` prepares it while retaining extra local packages.
No publishing is added to CI. CI checks the source change only.

## Install and manage a released CLI

After the chosen version has actually been released, users with `uv`, Bash and
curl installed can run one of these version-pinned commands (substitute the
published version and AntCode project):

```bash
curl -fsSL https://code.alipay.com/pd.pt/dogopencli/releases/download/v0.6.4/install.sh | bash
curl -fsSL https://github.com/proletariat64/dogopencli/releases/download/v0.6.4/install.sh | bash
```

The installer verifies the wheel SHA256 before uv replaces the program, selects
Python 3.12 and records the Release origin inside the tool environment. Downloads
require anonymous read access: AntCode releases are anonymous; a private GitHub
repository requires a separate authenticated download and local-wheel installation.
No token is embedded in the installer or installed origin marker.

On that host, no checkout or saved installer is required:

```bash
dogopencli update --to 0.6.5
dogopencli uninstall
```

`--to` explicitly selects a published stable version from the recorded provider;
there is no automatic latest-version lookup or downgrade. Updates download and
verify the wheel before replacement. `uninstall` removes only the active uv tool
installation. Configuration, browser profiles, installed leaves and Duckdog data
outside the program environment are retained. Keep custom data outside uv's tool
directory. No rollback environment or old program copy is kept.

For a source/wheel installation without a recorded Release origin:

```bash
dogopencli update --source /path/to/dogopencli-VERSION-py3-none-any.whl
dogopencli update --source /path/to/checkout
```

An explicit source clears the previous Release origin. Use the published installer
to switch providers and record the new origin. Custom `UV_TOOL_DIR` and
`UV_TOOL_BIN_DIR` must remain consistent. Commands refuse source/editable environments
or an environment that does not match the active uv tool.

## Plugin site

Build an immutable, checksummed site bundle independently of the CLI version:

```bash
make release-site SITE_VERSION=site-20261106
```

The bundle includes the standalone server, web assets, host validation code,
development guides, initial plugin seed and deployment helper. Deployment runs on
the target Linux host with Python 3.11+ and a working systemd user session:

```bash
make deploy-site SITE_BUNDLE=/path/to/uploaded-bundle SITE_ROOT=/home/admin/workspace/plugin-site
# Without a source checkout on the server:
python3 -B /path/to/uploaded-bundle/deploy.py --bundle /path/to/uploaded-bundle --root /home/admin/workspace/plugin-site
```

Transfer the complete bundle first using poolab or the host's existing transport.
The helper verifies all file hashes, copies to `releases/<version>`, seeds `data`
only on first deployment, switches `current`, installs/restarts the user service,
and checks that HTTP health reports the requested bundle version. A failed health
check restores the previous release and service unit. Same-version different bytes
are refused. Updates never copy seed over live published plugins or replace
`publish.env`. Input bundles must be outside the deployment root.

The helper owns only `plugin-site.service`. First-time nginx routing, DNS/TLS,
user-service lingering after logout and server permissions remain host setup;
see [site operations](../../tools/plugin-site/README.md). After that setup,
subsequent program deployments use the command above. To roll back, deploy the
previous retained input bundle; plugin data stays intact. There is no destructive
publication cleanup command.

## Plugin packages

Package one leaf using the existing static validator, then publish the exact ZIP:

```bash
make release-plugin PLUGIN=src/dogopencli/leaf_packages/collection/cost PLUGIN_DIST=dist/cost-release
make publish-plugin PLUGIN_ZIP=dist/cost-release/collection.cost.zip PLUGIN_VERSION=1.0.0 PLUGIN_SITE=https://registry.example/plugins/
```

Choose an existing leaf source directory and a new output directory. Set
`PLUGIN_PUBLISH_TOKEN` in the publisher's environment; do not put it in command
arguments or Git. HTTP requires explicit `ALLOW_HTTP=1` and should only be used
on the approved internal network or tunnel. The client rejects redirects, validates
the exact submitted ZIP without importing adapters, and verifies the downloaded
bytes after publication. Repeating the same identity/version succeeds only for
identical bytes; different bytes are rejected without overwrite. Registry versions
are independent release labels, not changes to the leaf manifest.

Static packaging/publication is not business UAT. Installing a published plugin
still uses `dogopencli plugins install <ZIP URL>`; the domain must be enabled.

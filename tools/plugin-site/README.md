# Dogopencli plugin site

A self-hosted registry under `/plugins/`: searchable catalog, domain filters,
release details, immutable ZIP downloads, authenticated publishing, and human/Agent
development guides. It uses the existing host static package validator without
importing uploaded adapters. Requires Linux and Python 3.11+; no service dependency
installation or frontend build is required on the server.

## Build and run locally

From the repository root, using the repository environment:

```bash
rtk proxy .venv/bin/python tools/plugin-site/build.py --output tmp/plugin-site-bundle --version source-634005c
rtk proxy cp -a tmp/plugin-site-bundle/seed tmp/plugin-site-data
rtk proxy python3 tmp/plugin-site-bundle/server.py --port 5910 --data tmp/plugin-site-data
```

Open `http://127.0.0.1:5910/plugins/`. The seed contains actual repository packages,
not mock cards. The version argument labels the registry release and is independent
of the manifest. Choose a fresh output directory for each build. Published records
show static validation only; neither the build nor registry proves business UAT.

To enable publishing, supply `PLUGIN_PUBLISH_TOKEN` in the server environment.
Without it the catalog/downloads work and publication returns 503. Use a strong
random token from a password manager. Do not commit it, print it, or persist it in
browser storage. The server binds loopback by default. HTTP sends credentials in
cleartext; publish only within a trusted company network or protected tunnel, or
put HTTPS in front of nginx. Registry access does not need domain login.

## Build and deploy commands

```bash
make release-site SITE_VERSION=site-20261106
```

This produces `dist/plugin-site/site-20261106` with a `bundle.json` checksum
manifest. Transfer the complete bundle to a staging directory on the target
host, then execute its `deploy.py` with Python 3.11+:

```bash
python3 -B /path/to/staged-bundle/deploy.py --bundle /path/to/staged-bundle --root /home/admin/workspace/plugin-site
```

On a host with a checkout, `make deploy-site SITE_BUNDLE=/path/to/staged-bundle`
is equivalent. The helper needs a working systemd user session; it installs and
enables `plugin-site.service`, switches `current`, checks the exact bundle version
at `/plugins/api/health`, and restores the previous release on health failure.
It seeds `data` only on first deployment. Later updates leave all plugin publications
and `publish.env` untouched; publish new plugin versions separately.

`make release-plugin` and `make publish-plugin` wrap the existing packer and the
new authenticated publisher. See [release and publication](../../docs/agents/releasing.md)
for arguments, retry behavior, curl CLI installation and provider selection.

## Host setup and transfer with poolab

The deployment helper runs locally on the target host. Before first deployment, inspect the actual server's nginx configuration, Python
path, available port and user service support. The provided paths assume the
`admin` user and must be confirmed at deployment time.

1. Sync the complete bundle to a NEW staging directory outside the deployment root:

   ```bash
   rtk proxy poolab sync tmp/plugin-site-bundle :/home/admin/workspace/plugin-site-staging/source-634005c --instance default
   ```

2. Run the helper from a staging directory outside the deployment root. It seeds
   `/home/admin/workspace/plugin-site/data` only if absent. On updates, publish
   new plugins explicitly; never replace live publications. Keep `data` and
   `publish.env` outside synchronized release trees.
3. Before running the helper, set the publisher token in a mode-0600
   `/home/admin/workspace/plugin-site/publish.env` file if publication is needed.
   Keep this file outside the release directory; the helper never writes it.
4. The helper switches `current`, installs the admin user service and checks health.
   Configure user-service lingering once if the service must survive logout.
5. Include `nginx.conf` inside the existing port-80 server block. Test nginx config
   before reload. Preserve existing routes. Add `<a href="/plugins/">Dogopencli
   插件广场</a>` to the existing homepage.
6. Check the public homepage link, catalog, ZIP bytes and authenticated publishing.
   Sync alone transfers files; running the service and nginx route completes hosting.

Expected public URL:
`http://poolab-iys595a7znqgza1e.inc.alipay.net/plugins/`.
Rollback switches `current` to the prior release and restarts the service; published
data remains outside release directories. No cleanup command deletes publications.

## API and verification

- `GET /plugins/api/catalog`: all releases with manifests and download URLs.
- `GET /plugins/api/health`: process health.
- `PUT /plugins/api/releases/<version>`: raw ZIP, bearer token, Content-Length.
- `GET /plugins/llms.txt` and `/plugins/agent-guide.md`: Agent entry points.

Successful upload returns 201; invalid packages 400; bad token 401; duplicate
identity/version 409; empty/oversize upload 413; disabled publishing 503.
Publication is serialized and committed by atomic directory rename. SHA256 reuses
the existing delivery integrity convention; it does not establish publisher trust.
Metadata and ZIPs persist together, and old versions remain downloadable.

Run focused tests with `rtk pytest -q tests/plugin_site`. Browser acceptance covers
search/filter/empty state, detail/download/version selection, docs, publish success
and error feedback, and narrow-screen layout. Tests use fake/local ZIPs and no
business APIs.

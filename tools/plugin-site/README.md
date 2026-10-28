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

## Deploy later with poolab

This repository task prepares deployment only. No remote files are changed.
After authorization, first inspect the actual server's nginx configuration, Python
path, available port and user service support. The provided paths assume the
`admin` user and must be confirmed at deployment time.

1. Sync the complete generated bundle to a NEW remote release directory:

   ```bash
   rtk proxy poolab sync tmp/plugin-site-bundle :/home/admin/workspace/plugin-site/releases/source-634005c --instance default
   ```

2. On first deployment only, copy the release's `seed` directory to
   `/home/admin/workspace/plugin-site/data`. On updates, merge only absent
   identity/version directories with the server stopped; never replace live
   publications. Keep `data` and `publish.env` outside synchronized release trees.
3. Point `/home/admin/workspace/plugin-site/current` to the new release. Set the
   publisher token in a mode-0600 `publish.env` file outside the release directory.
4. Install `plugin-site.service` as an admin user service (or use the environment's
   existing supervisor). Start/restart it and check `/plugins/api/health` locally.
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

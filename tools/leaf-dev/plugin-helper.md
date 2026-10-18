# Plugin author helper

Use a Python environment with `dogopencli` installed. From the repository root:

```bash
rtk proxy python tools/leaf-dev/plugin_helper.py verify /path/to/leaf-directory
rtk proxy python tools/leaf-dev/plugin_helper.py verify /path/to/delivery.zip
rtk proxy python tools/leaf-dev/plugin_helper.py pack /path/to/leaf-directory --output /path/to/delivery.zip
```

Choose an output outside the source directory with an existing parent directory.
Existing output is preserved and rejected, including symlinks. Verify accepts
local directories and ZIPs only. Pack validates an isolated source snapshot,
creates an ordinary ZIP, validates it again, and publishes only on success.
Identical package contents produce identical ZIP bytes regardless of source
timestamps and permissions. Keep the tested ZIP unchanged for HTTP delivery.
Success reports the manifest identity and `verified` or `packed`; failures exit
nonzero with a diagnostic. Preserve the source and correct the reported problem
before retrying with a new output path.

The host validator owns manifest rules, package limits and safe paths. A package
contains exactly one root `leaf.json`, its declared adapter, and optional README
and ordinary resources. Runtime configuration, credentials, caches and business
datasets are excluded. Manifest prose owns CLI help and GUI documentation;
README is independent supporting documentation.

Static verification does not import adapters or prove runtime or production
behavior. This helper performs no install, storage initialization, network
publication, dependency management or UAT. Installation and UAT remain separate
explicit operations.

For batch delivery and a short HTTP install/uninstall smoke, use the repository's
[migration procedure](workflow.md). Reuse a matching
verified host; leaf-only packages do not require rebuilding its wheel.

#!/usr/bin/env bash
# Rendered and attached to a specific Release by publish_release.py.
set -euo pipefail
VERSION='@VERSION@'
RELEASE_BASE_URL='@RELEASE_BASE_URL@'
WHEEL='@WHEEL@'
WHEEL_SHA256='@WHEEL_SHA256@'
command -v uv >/dev/null || { echo 'uv is required: https://docs.astral.sh/uv/' >&2; exit 1; }
command -v curl >/dev/null || { echo 'curl is required' >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    "$RELEASE_BASE_URL/$WHEEL" -o "$tmp/$WHEEL"
if command -v sha256sum >/dev/null; then
    digest=$(sha256sum "$tmp/$WHEEL")
else
    digest=$(shasum -a 256 "$tmp/$WHEEL")
fi
[[ ${digest%% *} == "$WHEEL_SHA256" ]] || { echo 'Wheel checksum mismatch' >&2; exit 1; }
# uv resolves/downloads before replacing the installed tool. Never pre-uninstall.
uv tool install --force --reinstall-package dogopencli --python 3.12 "dogopencli @ $tmp/$WHEEL"
tool_dir=$(uv tool dir)
printf '%s\n' "$RELEASE_BASE_URL" > "$tool_dir/dogopencli/.dogopencli-release"
bin_dir=$(uv tool dir --bin)
"$bin_dir/dogopencli" --version
printf 'Installed %s: %s/dogopencli\n' "$VERSION" "$bin_dir"
case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) printf 'Add to PATH: export PATH=%q:$PATH\n' "$bin_dir" ;;
esac

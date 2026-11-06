#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./install.sh install [SOURCE]
       ./install.sh update [SOURCE]
       ./install.sh uninstall

SOURCE is a checkout directory, wheel path, or direct HTTPS wheel URL.
The default source is the checkout containing this script.
Requires uv; Python 3.12 is selected (downloaded by uv if necessary).

install    Overwrite the single installed program, including the same version.
update     Uninstall the program, then install SOURCE. No rollback copy is kept.
uninstall  Remove the program and command; keep settings, login, plugins and data.

Uses uv's standard tool directories (UV_TOOL_DIR / UV_TOOL_BIN_DIR can override).
No development dependencies, editable install, backups or persistent download cache.
EOF
}

fail() {
    echo "error: $*" >&2
    exit 1
}

action=${1:---help}
case "$action" in
    -h|--help) usage; exit 0 ;;
    install|update) [[ $# -le 2 ]] || { usage >&2; exit 2; } ;;
    uninstall) [[ $# -eq 1 ]] || { usage >&2; exit 2; } ;;
    *) usage >&2; exit 2 ;;
esac

command -v uv >/dev/null 2>&1 || fail "uv is required: https://docs.astral.sh/uv/getting-started/installation/"

if [[ "$action" != uninstall ]]; then
    source=${2:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)}
    case "$source" in
        https://*) ;;
        *)
            if [[ -d "$source" && -f "$source/pyproject.toml" ]]; then
                source=$(cd -- "$source" && pwd -P)
            elif [[ -f "$source" && "$source" == *.whl ]]; then
                source="$(cd -- "$(dirname -- "$source")" && pwd -P)/$(basename -- "$source")"
            else
                fail "SOURCE must be a checkout directory, wheel path, or HTTPS wheel URL"
            fi
            ;;
    esac
fi

if [[ "$action" == uninstall || "$action" == update ]]; then
    tool_dir=$(uv tool dir)
    if [[ -e "$tool_dir/dogopencli" || -L "$tool_dir/dogopencli" ]]; then
        uv tool uninstall --no-cache dogopencli
    fi
fi

if [[ "$action" != uninstall ]]; then
    uv tool install --force --reinstall --no-cache --python 3.12 "dogopencli @ $source"
    bin_dir=$(uv tool dir --bin)
    "$bin_dir/dogopencli" --version
    echo "Installed: $bin_dir/dogopencli"
    case ":$PATH:" in
        *":$bin_dir:"*) ;;
        *) printf 'Add to PATH: export PATH=%q:$PATH\n' "$bin_dir" ;;
    esac
else
    echo "Uninstalled dogopencli. Settings, login, plugins and data were preserved."
fi

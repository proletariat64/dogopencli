"""Start an isolated worktree browser without borrowing existing authentication."""

import argparse
import json
import os
import shlex
import socket
import sys
from dataclasses import replace
from pathlib import Path

from dogopencli.auth.domains import authenticate_domains
from dogopencli.browser import launcher
from dogopencli.browser.coordination import acquire_file_lock
from dogopencli.browser.environment import (
    CHROME_BIN_ENV,
    DEFAULT_CHROME_BIN,
    FORBIDDEN_PORTS,
    STARTUP_URLS,
    BrowserEnvironment,
    _auth_section,
    cdp_port,
)
from dogopencli.browser.errors import AuthError
from dogopencli.browser.login import login
from dogopencli.domains import DomainService
from dogopencli.errors import CliError


def available_port() -> int:
    """Ask the OS for an unused loopback port outside the reserved range."""
    while True:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        if port not in FORBIDDEN_PORTS:
            return port


def setup(root: Path) -> BrowserEnvironment:
    root = root.resolve()
    directory = root / "tmp/bootstrap-browser"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.resolve() != directory:
        raise RuntimeError("bootstrap browser directory must not be a symlink")
    directory.chmod(0o700)
    lock = acquire_file_lock(directory / ".setup.lock")
    try:
        config = directory / "config.toml"
        profile = directory / "chrome"
        if config.exists():
            # Read only this generated config, ignoring shared auth overrides.
            section = _auth_section(config)
            if section.get("profile") != str(profile):
                raise RuntimeError("bootstrap config belongs to another worktree")
            port = cdp_port(section.get("cdp_url", ""))
            if section["cdp_url"] != f"http://127.0.0.1:{port}":
                raise RuntimeError("bootstrap CDP must bind to IPv4 loopback")
            chrome_bin = section.get("chrome_bin", DEFAULT_CHROME_BIN)
        else:
            port = available_port()
            chrome_bin = os.environ.get(CHROME_BIN_ENV) or DEFAULT_CHROME_BIN
            config.write_text(
                "[auth]\n"
                f"profile = {json.dumps(str(profile))}\n"
                f"cdp_url = {json.dumps(f'http://127.0.0.1:{port}')}\n"
                f"chrome_bin = {json.dumps(chrome_bin)}\n\n"
                "[cache]\n"
                f"path = {json.dumps(str(directory / 'cache.sqlite3'))}\n"
            )
            config.chmod(0o600)
        if profile.resolve() != profile:
            raise RuntimeError("bootstrap Chrome profile must not be a symlink")
        profile.mkdir(mode=0o700, exist_ok=True)
        profile.chmod(0o700)
        environment = BrowserEnvironment(
            cdp_url=f"http://127.0.0.1:{port}",
            profile=profile,
            startup_url="about:blank",
            chrome_bin=chrome_bin,
            log_path=directory / "chrome.log",
        )
        # Preserve a verified browser's current mode and tabs, including human SSO.
        # launch() verifies listener/profile ownership before allowing any reuse.
        metadata = launcher._cdp_metadata(environment.cdp_url)
        if not metadata:
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError(
                        "bootstrap CDP port is occupied; browser preserved"
                    )
            owner = launcher._Owner(profile / launcher.OWNER_FILE_NAME)
            if owner.is_valid(profile):
                raise RuntimeError(
                    "owned browser is running without CDP; browser preserved"
                )
        mode = launcher._metadata_mode(metadata) if metadata else "headless"
        print(launcher.launch(environment, mode))
        shell = directory / "env.sh"
        shell.write_text(
            "# Worktree-local configuration; source from the calling shell.\n"
            "unset DOGOPENCLI_CONFIG DOGOPENCLI_CHROME_PROFILE "
            "DOGOPENCLI_CHROME_CDP_URL DOGOPENCLI_CHROME_LOG "
            "DOGOPENCLI_CHROME_BIN\n"
            f"export DOGOPENCLI_CONFIG_DIR={shlex.quote(str(directory))}\n"
        )
        shell.chmod(0o600)
        print(f"Activate isolated config: source {shlex.quote(str(shell))}")
        return environment
    finally:
        lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domain",
        choices=STARTUP_URLS,
        help="also verify domain authentication and complete human SSO if needed",
    )
    args = parser.parse_args(argv)
    try:
        environment = setup(Path(__file__).resolve().parents[1])
        domains = DomainService(config_file=environment.profile.parent / "config.toml")
        if args.domain is not None:
            print(
                f"Verifying isolated {args.domain} login; "
                "complete SSO if Chrome opens.",
                flush=True,
            )
            login(replace(environment, startup_url=STARTUP_URLS[args.domain]))
            print(f"{args.domain} authentication verified headless")
        print(
            "Checking enabled domain authentication (no automatic SSO)...", flush=True
        )
        try:
            verdict = authenticate_domains(environment, domains, None, recover=False)
            outcomes = verdict.get("domains", [verdict])
        except AuthError as error:
            if error.code == "interrupted":
                raise KeyboardInterrupt from error
            outcomes = error.details.get("domains") or [
                {"domain": "all", "error": {"code": error.code}}
            ]
        print_startup_prompt(environment, outcomes)
        return 0
    except KeyboardInterrupt:
        print("bootstrap browser: interrupted; browser preserved", file=sys.stderr)
        return 130
    except (
        OSError,
        RuntimeError,
        AuthError,
        CliError,
        launcher.LauncherError,
    ) as error:
        code = f"{error.code}: " if isinstance(error, AuthError) else ""
        print(f"bootstrap browser: {code}{error}", file=sys.stderr)
        return 1


def print_startup_prompt(environment: BrowserEnvironment, outcomes: list[dict]) -> None:
    """Print a copyable handoff with current browser and observed auth status."""
    metadata = launcher._cdp_metadata(environment.cdp_url)
    if not metadata:
        raise RuntimeError("CDP unavailable after domain auth check")
    mode = launcher._metadata_mode(metadata)
    owner = launcher._Owner(environment.profile / launcher.OWNER_FILE_NAME)
    pid = (
        owner.pid
        if owner.is_valid(environment.profile)
        else launcher._profile_lock_pid(environment.profile)
    )
    print("\n----start up prompts-----------------------------------------------------")
    print("$caveman\n")
    print(
        "- This worktree is ready for development; UAT requires domain authentication."
    )
    print("- Prepared isolated Chrome profile and CDP settings for future UAT.")
    print(f"    Chrome mode {mode}")
    print(f"    pid {pid if pid is not None else 'unknown'}")
    print(f"    CDP {environment.cdp_url}")
    print(f"    profile: {environment.profile}")
    print("    bootstrap browser: PASS; isolated browser ready")
    print("    domain auth check:")
    for outcome in outcomes:
        status = (
            "authenticated"
            if outcome.get("authenticated") is True
            else outcome.get("error", {}).get("code", "unknown")
        )
        print(f"      {outcome['domain']}: {status}")
    shell = shlex.quote(str(environment.profile.parent / "env.sh"))
    print(f"- Activate isolated config: source {shell}")
    print("- If authentication is required: dogopencli login")
    print("-------------------------------------------------------------------------")


if __name__ == "__main__":
    raise SystemExit(main())

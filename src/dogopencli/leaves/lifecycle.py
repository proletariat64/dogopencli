"""Explicit, bounded leaf installation and removal under host ownership locks."""

import fcntl
import os
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from ..cache import Cache
from ..domains import DomainService
from ..errors import LOCKED, CliError
from .registry import Registry


@contextmanager
def lifecycle_lock(registry: Registry) -> Iterator[None]:
    """Use the same lock/inode as registration; never reconcile other leaves."""
    directory = registry.config_file.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(directory / "leaf-registry.lock", os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as error:
        raise CliError("IO_ERROR", "Cannot open plugin lifecycle lock") from error
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise CliError(
                LOCKED, "Plugin lifecycle is busy", retryable=True
            ) from error
        yield
    finally:
        os.close(fd)


def _local_directory(path: Path, *, create: bool = False) -> bool:
    try:
        status = path.lstat()
    except FileNotFoundError:
        if not create:
            return False
        path.mkdir()
        status = path.lstat()
    if path.is_symlink() or not path.is_dir():
        raise CliError("IO_ERROR", "Plugin root/domain must be a local directory")
    # Reading the directory distinguishes unavailable roots from absent leaves.
    with os.scandir(path):
        pass
    return bool(status)


@contextmanager
def _state(registry: Registry) -> Iterator[sqlite3.Connection]:
    with closing(
        sqlite3.connect(
            registry.config_file.parent / "leaf-registry.sqlite3", timeout=0
        )
    ) as state:
        state.execute("BEGIN IMMEDIATE")
        state.execute(
            "CREATE TABLE IF NOT EXISTS bindings (leaf_id TEXT PRIMARY KEY, "
            "database_path TEXT NOT NULL, relation_name TEXT NOT NULL, "
            "active INTEGER NOT NULL, UNIQUE(database_path, relation_name))"
        )
        try:
            yield state
            state.commit()
        except BaseException:
            state.rollback()
            raise


def install(config_file: Path, source: str) -> dict:
    from .package import prepare_package

    registry = Registry(config_file)
    published = False
    destination = None
    try:
        with prepare_package(source) as package:
            domain, name = package.manifest["domain"], package.manifest["name"]
            identity = f"{domain}.{name}"
            # Inventory receives declarations, so domain checks cannot load adapters.
            service = DomainService(config_file, registry=registry)
            if not service.inventory(domain)[0]["enabled"]:
                raise CliError("DOMAIN_DISABLED", f"Domain is disabled: {domain}")
            with lifecycle_lock(registry):
                _local_directory(registry.root, create=True)
                _local_directory(registry.root / domain, create=True)
                destination = registry.root / domain / name
                if os.path.lexists(destination):
                    raise CliError(
                        "PLUGIN_EXISTS", f"Leaf already installed: {identity}"
                    )
                with tempfile.TemporaryDirectory(
                    prefix=".leaf-install-", dir=registry.config_file.parent
                ) as temporary:
                    staging = Path(temporary) / domain / name
                    staging.parent.mkdir()
                    shutil.copytree(package.path, staging)
                    leaf = registry._load(staging)
                    with _state(registry) as state:
                        previous = state.execute(
                            "SELECT * FROM bindings WHERE leaf_id=?", (identity,)
                        ).fetchone()

                        def publish() -> None:
                            nonlocal published
                            # Rename within this filesystem is atomic to discovery.
                            staging.rename(destination)
                            published = True
                            state.commit()

                        try:
                            registry._storage(leaf, state, publish=publish)
                        except BaseException:
                            if published:
                                destination.rename(staging)
                                published = False
                                # DuckDB commit can fail after SQLite commit. Restore
                                # only this operation's binding, never other leaves.
                                state.execute(
                                    "DELETE FROM bindings WHERE leaf_id=?", (identity,)
                                )
                                if previous:
                                    state.execute(
                                        "INSERT INTO bindings VALUES (?, ?, ?, ?)",
                                        previous,
                                    )
                                state.commit()
                            raise
            return {"installed": identity, "path": str(destination), "diagnostics": []}
    except CliError:
        raise
    except sqlite3.OperationalError as error:
        if "locked" in str(error).lower():
            raise CliError(LOCKED, "Plugin storage is busy", retryable=True) from error
        raise CliError("DATASET_ERROR", "Cannot update plugin ownership") from error
    except (OSError, sqlite3.Error) as error:
        raise CliError(
            "IO_ERROR", "Plugin installation failed; retry after checking local storage"
        ) from error
    except Exception as error:
        raise CliError(
            "INVALID_LEAF",
            "Adapter validation failed; inspect package and retained storage",
        ) from error


def uninstall(config_file: Path, identity: str) -> dict:
    if not re.fullmatch(
        r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", identity
    ):
        raise CliError(
            "INVALID_ARGUMENT", "Use full domain.dotted-leaf identity", exit_code=2
        )
    domain, name = identity.split(".", 1)
    registry = Registry(config_file)
    destination = registry.root / domain / name
    removed = False
    cache_removed = False
    try:
        with lifecycle_lock(registry):
            root_present = _local_directory(registry.root)
            domain_present = root_present and _local_directory(registry.root / domain)
            present = domain_present and os.path.lexists(destination)
            # The leaf itself may be broken, including a symlink. Move the entry
            # without following it; no manifest or adapter needs to be loaded.
            with Cache(registry.cache_path).refresh_lock():
                with tempfile.TemporaryDirectory(
                    prefix=".leaf-uninstall-", dir=registry.config_file.parent
                ) as temporary:
                    tombstone = Path(temporary) / "removed"
                    if present:
                        destination.rename(tombstone)
                        removed = True
                    try:
                        with _state(registry) as state:
                            cache_removed = Cache(registry.cache_path).remove(
                                "leaf:" + identity
                            )
                            state.execute(
                                "UPDATE bindings SET active=0 WHERE leaf_id=?",
                                (identity,),
                            )
                        if removed:
                            if tombstone.is_symlink() or not tombstone.is_dir():
                                tombstone.unlink()
                            else:
                                shutil.rmtree(tombstone)
                    except BaseException:
                        if removed and os.path.lexists(tombstone):
                            tombstone.rename(destination)
                        raise
        return {
            "uninstalled": identity,
            "removed": removed,
            "cache_removed": cache_removed,
            "data_retained": True,
        }
    except CliError:
        raise
    except sqlite3.OperationalError as error:
        if "locked" in str(error).lower():
            raise CliError(LOCKED, "Plugin storage is busy", retryable=True) from error
        raise CliError("IO_ERROR", "Cannot update plugin ownership") from error
    except (OSError, sqlite3.Error) as error:
        raise CliError(
            "IO_ERROR", "Plugin removal failed; check root availability and storage"
        ) from error

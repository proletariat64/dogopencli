"""Optional read-only DuckDB selector boundary."""

import pytest

from dogopencli.duckdog import resolve_selector
from dogopencli.errors import CliError


def test_selector_preserves_native_case_deduplicates_and_anchors_path(
    tmp_path, monkeypatch
):
    duckdb = pytest.importorskip("duckdb")

    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute('CREATE TABLE "native entities" ("instId" VARCHAR)')
        connection.executemany(
            'INSERT INTO "native entities" VALUES (?)',
            [("Alpha",), ("alpha",), ("Alpha",)],
        )
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/reference/entities" = "native entities"\n'
    )
    before = database.read_bytes()
    monkeypatch.chdir(tmp_path.parent)
    assert resolve_selector(
        "liquidity/reference/entities", "instId", config_file=config
    ) == ["Alpha", "alpha"]
    assert database.read_bytes() == before


@pytest.mark.parametrize("values", [[None], [""], [" "], [" A"], ["A/B"], []])
def test_invalid_or_empty_selector_withholds_universe(tmp_path, values):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute('CREATE TABLE entities ("instId" VARCHAR)')
        for value in values:
            connection.execute("INSERT INTO entities VALUES (?)", [value])
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/reference/entities" = "entities"\n'
    )
    with pytest.raises(CliError, match="malformed|empty"):
        resolve_selector("liquidity/reference/entities", "instId", config_file=config)


def test_selector_does_not_coerce_numeric_ids(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute('CREATE TABLE entities ("instId" INTEGER)')
        connection.execute("INSERT INTO entities VALUES (123)")
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/reference/entities" = "entities"\n'
    )
    with pytest.raises(CliError, match="malformed"):
        resolve_selector("liquidity/reference/entities", "instId", config_file=config)


@pytest.mark.parametrize(
    "relation",
    ["absent", "entities; DROP TABLE entities", 'entities"; DROP TABLE entities;--'],
)
def test_missing_or_sql_like_mapping_cannot_execute_sql(tmp_path, relation):
    duckdb = pytest.importorskip("duckdb")
    import json

    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute('CREATE TABLE entities ("instId" VARCHAR)')
        connection.execute("INSERT INTO entities VALUES ('ALIPAYGM')")
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "native.duckdb"\n[duckdog.selectors]\n'
        f'"liquidity/reference/entities" = {json.dumps(relation)}\n'
    )
    before = database.read_bytes()
    with pytest.raises(CliError, match="cannot be read"):
        resolve_selector("liquidity/reference/entities", "instId", config_file=config)
    assert database.read_bytes() == before


def test_missing_database_is_never_created(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "absent.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/reference/entities" = "entities"\n'
    )
    with pytest.raises(CliError, match="missing"):
        resolve_selector("liquidity/reference/entities", "instId", config_file=config)
    assert not (tmp_path / "absent.duckdb").exists()


def test_unregistered_binding_fails_without_config_or_database():
    with pytest.raises(CliError, match="not registered"):
        resolve_selector("fx/trades", "uniqueId", config_file=None)


def test_missing_dependency_is_actionable(tmp_path, monkeypatch):
    import sys

    database = tmp_path / "native.duckdb"
    database.touch()
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/reference/entities" = "entities"\n'
    )
    monkeypatch.setitem(sys.modules, "duckdb", None)
    with pytest.raises(CliError, match="required; reinstall dogopencli"):
        resolve_selector("liquidity/reference/entities", "instId", config_file=config)
    assert database.read_bytes() == b""


def test_missing_native_column_does_not_use_display_id(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE TABLE entities (instCode VARCHAR, id INTEGER)")
        connection.execute("INSERT INTO entities VALUES ('Z17', 10)")
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/reference/entities" = "entities"\n'
    )
    with pytest.raises(CliError, match="native column"):
        resolve_selector("liquidity/reference/entities", "instId", config_file=config)


def test_selector_order_is_stable_under_case_insensitive_source_collation(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute('CREATE TABLE entities ("instId" VARCHAR COLLATE NOCASE)')
        connection.execute(
            "INSERT INTO entities VALUES ('alpha'), ('Alpha'), ('alpha')"
        )
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath = "native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/reference/entities" = "entities"\n'
    )
    assert resolve_selector(
        "liquidity/reference/entities", "instId", config_file=config
    ) == ["Alpha", "alpha"]

"""Read-only cash-account record binding used by online context resolution."""

import pytest

from dogopencli.duckdog import AccountSourceUnavailable, read_account_records
from dogopencli.errors import CliError


def test_account_reader_preserves_relation_order_and_native_ownership(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "accounts.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            'CREATE TABLE accounts ("aliasName" VARCHAR, "instId" VARCHAR, '
            '"bankId" VARCHAR, "instCode" VARCHAR, id INTEGER)'
        )
        connection.execute(
            "INSERT INTO accounts VALUES ('A', 'SECOND', 'B2', 'Z21', 1), "
            "('A', 'FIRST', 'B1', 'Z17', 2)"
        )
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath="accounts.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/cash/accounts"="accounts"\n'
    )
    before = database.read_bytes()
    assert read_account_records(config_file=config) == [
        {"aliasName": "A", "instId": "SECOND", "bankId": "B2"},
        {"aliasName": "A", "instId": "FIRST", "bankId": "B1"},
    ]
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "contents",
    [None, "[sources]\n", '[duckdog]\npath="absent.duckdb"\n[duckdog.selectors]\n'],
)
def test_unconfigured_account_source_is_unavailable(tmp_path, contents):
    config = tmp_path / "config.toml"
    if contents is not None:
        config.write_text(contents)
    with pytest.raises(AccountSourceUnavailable):
        read_account_records(config_file=config)


def test_configured_missing_database_is_real_error_and_never_created(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath="absent.duckdb"\n[duckdog.selectors]\n"liquidity/cash/accounts"="accounts"\n'
    )
    with pytest.raises(CliError, match="database is missing"):
        read_account_records(config_file=config)
    assert not (tmp_path / "absent.duckdb").exists()


def test_invalid_configured_database_does_not_become_unavailable(tmp_path):
    database = tmp_path / "bad.duckdb"
    database.write_text("corrupt")
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath="bad.duckdb"\n[duckdog.selectors]\n"liquidity/cash/accounts"="accounts"\n'
    )
    with pytest.raises(CliError, match="cannot be read"):
        read_account_records(config_file=config)
    assert database.read_text() == "corrupt"


def test_missing_required_dependency_is_an_installation_error(tmp_path, monkeypatch):
    import sys

    (tmp_path / "native.duckdb").touch()
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath="native.duckdb"\n[duckdog.selectors]\n"liquidity/cash/accounts"="accounts"\n'
    )
    monkeypatch.setitem(sys.modules, "duckdb", None)
    with pytest.raises(CliError, match="required; reinstall dogopencli"):
        read_account_records(config_file=config)


@pytest.mark.parametrize("relation", ["missing", 'accounts"; DROP TABLE accounts;--'])
def test_missing_or_sql_like_account_mapping_is_real_read_failure(tmp_path, relation):
    import json

    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute('CREATE TABLE accounts ("aliasName" VARCHAR)')
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath="native.duckdb"\n[duckdog.selectors]\n"liquidity/cash/accounts"='
        + json.dumps(relation)
        + "\n"
    )
    before = database.read_bytes()
    with pytest.raises(CliError, match="cannot be read"):
        read_account_records(config_file=config)
    assert database.read_bytes() == before


def test_account_record_budget_rejects_truncation(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE accounts AS SELECT 'A' AS \"aliasName\", "
            "'B' AS \"bankId\", 'E' AS \"instId\" FROM range(100001)"
        )
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath="native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/cash/accounts"="accounts"\n'
    )
    with pytest.raises(CliError, match="read budget"):
        read_account_records(config_file=config)


def test_account_records_never_coerce_non_string_ownership(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    database = tmp_path / "native.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            'CREATE TABLE accounts ("aliasName" VARCHAR, "instId" INTEGER)'
        )
        connection.execute("INSERT INTO accounts VALUES ('A', 123)")
    config = tmp_path / "config.toml"
    config.write_text(
        '[duckdog]\npath="native.duckdb"\n[duckdog.selectors]\n'
        '"liquidity/cash/accounts"="accounts"\n'
    )
    with pytest.raises(CliError, match="malformed"):
        read_account_records(config_file=config)

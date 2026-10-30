"""Static opt-in calendar declarations and activation signature acceptance."""

import json

import pytest
from test_leaf_registry import install

from dogopencli.errors import CliError
from dogopencli.leaves.registry import validate_manifest


def declared(tmp_path):
    folder = install(tmp_path)
    value = json.loads((folder / "leaf.json").read_text())
    value["operations"]["list"]["parameters"] = [
        {"name": name, "type": "string", "required": True, "description": "Date"}
        for name in ("from-date", "to-date")
    ]
    value["operations"]["list"]["history"] = {
        "interpretation": "calendar_date",
        "time_basis": "valueDate",
        "boundary": "inclusive",
        "timezone": None,
        "from_parameter": "from-date",
        "to_parameter": "to-date",
        "splitting": "explicit_windows",
        "cross_range_equivalence": False,
    }
    return value


def test_temporal_declaration_requires_declared_date_parameters(tmp_path):
    value = declared(tmp_path)
    value["operations"]["list"]["history"]["from_parameter"] = "missing"
    with pytest.raises(CliError, match="history"):
        validate_manifest(value)


@pytest.mark.parametrize(
    "change",
    [
        {"to_parameter": "from-date"},
        {"from_parameter": "start-date"},
        {"timezone": 8},
        {"time_basis": ""},
        {"max_day_difference": -1},
        {"max_day_difference": True},
        {"interpretation": "instant"},
        {"cross_range_equivalence": True},
        {"format": "%Y%m%d"},
        {"applicability": {"parameter": "source", "values": ["market"]}},
    ],
)
def test_temporal_declaration_rejects_unsupported_contracts(tmp_path, change):
    value = declared(tmp_path)
    value["operations"]["list"]["history"].update(change)
    with pytest.raises(CliError):
        validate_manifest(value)


def test_temporal_declaration_accepts_unknown_timezone_and_source_condition(tmp_path):
    value = declared(tmp_path)
    value["operations"]["list"]["parameters"].append(
        {
            "name": "source",
            "type": "string",
            "required": True,
            "description": "Rate source",
            "choices": ["market", "bank", "rule"],
        }
    )
    value["operations"]["list"]["history"].update(
        {
            "max_day_difference": 0,
            "applicability": {"parameter": "source", "values": ["market", "bank"]},
        }
    )
    validate_manifest(value)


def test_activation_requires_date_conversion_signatures_without_executing_them(
    tmp_path, run_cli, monkeypatch
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(tmp_path / "config"))

    value = declared(tmp_path)
    folder = tmp_path / "plugins/payment/sample"
    (folder / "leaf.json").write_text(json.dumps(value))
    code, output, _ = run_cli(["plugins", "install", str(folder)])
    assert code == 1, output
    assert "declared operations" in output
    adapter = folder / "adapter.py"
    adapter.write_text(
        adapter.read_text().replace(
            "adapter = Adapter()",
            """
    def history_bounds(self, parameters): raise AssertionError('must not execute')
    def history_parameters(self, bounds): raise AssertionError('must not execute')
adapter = Adapter()""",
        )
    )
    code, output, _ = run_cli(["plugins", "install", str(folder)])
    assert code == 0, output

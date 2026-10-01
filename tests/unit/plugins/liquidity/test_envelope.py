"""Liquidity envelope parsing: success markers, refusals, malformed shapes."""

import json

import pytest

from dogopencli.errors import BUSINESS_QUERY_FAILED, INVALID_RESPONSE, CliError
from dogopencli.plugins.liquidity import spec
from dogopencli.plugins.liquidity.envelope import dig, envelope_document


def body(document) -> bytes:
    return json.dumps(document).encode()


def test_success_envelope_returns_document():
    node = envelope_document(
        body({"success": True, "data": {"x": 1}}), spec.ENV_SUCCESS
    )
    assert node["data"] == {"x": 1}


def test_success_envelope_rejects_refusal_and_missing_marker():
    for document in (
        {"success": False, "errorCode": "099", "data": None},
        {"data": {"x": 1}},
        {"success": "true", "data": {}},
    ):
        with pytest.raises(CliError) as error:
            envelope_document(body(document), spec.ENV_SUCCESS)
        assert error.value.code == BUSINESS_QUERY_FAILED


def test_base_result_envelope():
    node = envelope_document(
        body({"baseResult": {"success": True, "data": {"orderNo": "A1"}}}),
        spec.ENV_BASE_RESULT,
    )
    assert node["baseResult"]["data"]["orderNo"] == "A1"
    with pytest.raises(CliError) as error:
        envelope_document(
            body({"baseResult": {"success": False}}), spec.ENV_BASE_RESULT
        )
    assert error.value.code == BUSINESS_QUERY_FAILED


def test_result_flag_envelope_checks_inner_success():
    node = envelope_document(
        body({"resultFlag": True, "result": {"count": 2, "dataValue": [1, 2]}}),
        spec.ENV_RESULT_FLAG,
    )
    assert node["result"]["count"] == 2
    # Permission failure shape observed 2026-10-01: both markers false.
    with pytest.raises(CliError) as error:
        envelope_document(
            body({"resultFlag": False, "result": {"success": False}}),
            spec.ENV_RESULT_FLAG,
        )
    assert error.value.code == BUSINESS_QUERY_FAILED
    # Outer true with an explicit inner refusal is still a refusal.
    with pytest.raises(CliError) as error:
        envelope_document(
            body({"resultFlag": True, "result": {"success": False}}),
            spec.ENV_RESULT_FLAG,
        )
    assert error.value.code == BUSINESS_QUERY_FAILED


def test_result_success_envelope():
    node = envelope_document(
        body({"success": True, "result": {"transferRuleVO": {"ruleId": "R1"}}}),
        spec.ENV_RESULT_SUCCESS,
    )
    assert node["result"]["transferRuleVO"]["ruleId"] == "R1"


def test_malformed_bodies_are_invalid_response():
    for raw in (b"not json", b"[1, 2]", b'"text"'):
        with pytest.raises(CliError) as error:
            envelope_document(raw, spec.ENV_SUCCESS)
        assert error.value.code == INVALID_RESPONSE


def test_dig_exact_path():
    node = {"data": {"data": [1], "totalCount": 1}}
    assert dig(node, ("data", "data")) == [1]
    with pytest.raises(CliError) as error:
        dig(node, ("data", "missing"))
    assert error.value.code == INVALID_RESPONSE

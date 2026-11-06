"""Malformed frozen contracts must fail with qualified diagnostics."""

import pytest

from dogopencli.errors import CliError
from dogopencli.workflow_import_qualification import contract_rules


@pytest.mark.parametrize("missing", ["component", "retention", "diagnostic_code"])
def test_frozen_matcher_missing_required_key_is_rejected(missing):
    matcher = {
        "component": "detail",
        "retention": "failed",
        "diagnostic_code": "BUSINESS_QUERY_FAILED",
        "native_code": "999",
    }
    del matcher[missing]
    artifact = {
        "import_qualification": {
            "version": 1,
            "rules": [
                {
                    "id": "detail",
                    "action": "preserve",
                    "reason_codes": [],
                    "retained_errors": [matcher],
                }
            ],
        }
    }
    with pytest.raises(CliError) as error:
        contract_rules(artifact)
    assert error.value.code == "WORKFLOW_IMPORT_NOT_QUALIFIED"
    assert error.value.meta["diagnostic"]["reason_codes"] == ["INSUFFICIENT_EVIDENCE"]

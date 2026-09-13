"""Shared evidence vocabulary for offline schemas and reading guides."""

from copy import deepcopy
from typing import Any

_VOCABULARY = {
    "x-evidence": {
        "dimensions": {
            "type": "Evidence for JSON type; only verified types constrain values.",
            "presence": "Presence evidence; observed does not mean required.",
            "nullability": "Nullability evidence; unknown remains open.",
            "unit": "Unit evidence; unknown prohibits inferred conversion.",
            "meaning": "Evidence for business interpretation.",
        },
        "values": {
            "verified": "Guaranteed by CLI behavior or explicit verification.",
            "observed": "Seen in documented samples, not a universal constraint.",
            "unknown": "Unresolved; no guarantee or semantic inference.",
            "not_applicable": "Dimension does not apply to this description.",
        },
    },
    "x-observed-type": "Observed JSON type only; not a validation assertion.",
    "x-observed-values": "Non-exhaustive observed values, never a closed enum.",
    "x-unit": "Unit name when explicitly verified; no automatic conversion.",
}


def schema_annotations() -> dict[str, Any]:
    """Schema-local annotation definitions, independent of business fields."""
    return deepcopy(_VOCABULARY)


def guide_annotations() -> dict[str, Any]:
    """Reading-guide presentation of the same evidence dimensions and values."""
    annotations = schema_annotations()
    evidence = annotations["x-evidence"]
    evidence["aspects"] = list(evidence.pop("dimensions"))
    evidence["description"] = (
        "Evidence for each independent aspect; observation is not a guarantee."
    )
    annotations["x-annotation-vocabulary"] = (
        "Schema-local definitions of the annotation keys."
    )
    return annotations

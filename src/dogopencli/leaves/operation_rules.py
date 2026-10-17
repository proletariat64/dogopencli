"""Declaration-only projections of shared host operation rules.

Known errors are not an exhaustive adapter contract. Consumers must tolerate
unknown codes. Keep these groups tied to host execution, not individual leaves.
"""

# leaves.cli resolves declarations before activation. Registry.get preserves
# discovery/activation diagnostics; the shell catches unexpected failures.
DECLARATION_ERRORS = (
    "INVALID_ARGUMENT",
    "LEAF_NOT_FOUND",
    "INVALID_LEAF",
    "LEAF_LOAD_ERROR",
    "CONFIG_ERROR",
    "INTERNAL_ERROR",
)
# Registry.scan and DomainService precede runtime.execute for these operations.
EXECUTION_ERRORS = ("DOMAIN_STATE_ERROR", "LOCKED", "IO_ERROR", "CACHE_ERROR")
# inquiry._map_auth_error and shared transport/collection validation.
INQUIRY_ERRORS = (
    "AUTH_REQUIRED",
    "BROWSER_UNAVAILABLE",
    "REQUEST_NOT_ALLOWED",
    "TIMEOUT",
    "BUSINESS_QUERY_FAILED",
    "INVALID_RESPONSE",
)
# runtime.execute's cached-list branch; result_policy.check_complete is shared
# by cached/live list and refresh, but is not a get/prune/describe policy.
CACHE_READ_ERRORS = ("CACHE_MISS", "CACHE_STALE", "CACHE_CONTRACT_CHANGED")


def known_errors(operation: str, *, has_list: bool) -> tuple[str, ...]:
    errors = list(DECLARATION_ERRORS)
    if operation != "describe":
        errors.extend(EXECUTION_ERRORS)
        if has_list:
            errors.append("DATASET_ERROR")
        if operation != "prune":
            errors.append("DOMAIN_DISABLED")
    if operation in {"list", "get", "refresh"}:
        errors.extend(INQUIRY_ERRORS)
    if operation in {"list", "refresh"}:
        errors.append("INCOMPLETE_RESULT")
    if operation == "list":
        errors.extend(CACHE_READ_ERRORS)
    return tuple(dict.fromkeys(errors))

"""Native asset root and physical quotation-group version inquiries (#141)."""

from typing import Any

from ...errors import INVALID_RESPONSE, CliError
from .spec import (
    ENC_FORM,
    ENV_SUCCESS,
    RUNTIMES,
    SETTINGS,
    TENANT,
    DetailSpec,
    IdentityOption,
)

ASSET_FIELDS = (
    "orderNo",
    "accountingEntityCode",
    "actualValueDate",
    "aliasName",
    "assetProductVo",
    "assetTransferAmount",
    "assetTransferCurrency",
    "bankId",
    "counterpartTransferAmount",
    "counterpartyAccountCurrency",
    "counterpartyAccountingEntityCode",
    "counterpartyAliasName",
    "counterpartyBankId",
    "counterpartyLegalEntityCode",
    "counterpartyTransferCurrency",
    "currency",
    "digitalCurrencyCategory",
    "endToEndId",
    "finNetId",
    "globalOrderId",
    "gmtCreate",
    "gmtCreditReturn",
    "gmtDebitReturn",
    "gmtModified",
    "gmtSend",
    "legalEntityCode",
    "orderStatus",
    "peggedCurrency",
    "purposeCode",
    "referDigitalCurrency",
    "reportId",
    "retryTimes",
    "source",
    "timezone",
    "tradingDate",
    "transactionType",
    "tntInstId",
)
PRODUCT_FIELDS = (
    "assertProductCategory",
    "assertProductCode",
    "assertProductName",
    "assertProductTenor",
    "assertProductType",
)
ASSET_DETAIL = DetailSpec(
    path=("operations", "asset-trades"),
    action="get",
    kind=RUNTIMES,
    title="asset-transfer trading root detail",
    endpoint="/assetTransferOrderDetailQuery.json",
    method="POST",
    encoding=ENC_FORM,
    envelope=ENV_SUCCESS,
    container=("data",),
    tenant_field=False,
    identity=(
        IdentityOption(
            "order_no", "orderNo", "Nonempty native root order number.", echo="orderNo"
        ),
    ),
    list_leaf=("operations", "asset-trades"),
    projection="asset_trade_detail",
    schema_version="asset-trade-detail-v1",
    table_columns=(
        "orderNo",
        "tradingDate",
        "orderStatus",
        "assetTransferAmount",
        "assetTransferCurrency",
    ),
    notes=(
        "Exactly one form POST sends only orderNo; native data.orderNo must match.",
        "Trading root and native assetProductVo only; "
        "transFerOrderLogVoList has unproved ownership and is excluded.",
        "Native product keys retain source spelling "
        "assertProductCategory/Code/Name/Tenor/Type.",
        "Amounts, currencies, dates, unknown states, "
        "blank/null/absence stay native; capture time is separate.",
        "Authenticated tenant scope is metadata; absent native "
        "tenant echo is never fabricated.",
    ),
)


def project_asset_detail(row: dict[str, Any]) -> dict[str, Any]:
    tenant = row.get("tntInstId")
    if tenant is not None and tenant != "" and tenant != TENANT:
        raise CliError(
            INVALID_RESPONSE, "asset detail tenant contradicts request scope"
        )
    result = {field: row[field] for field in ASSET_FIELDS if field in row}
    if "assetProductVo" in row and row["assetProductVo"] is not None:
        product = row["assetProductVo"]
        if not isinstance(product, dict):
            raise CliError(INVALID_RESPONSE, "asset product detail is not an object")
        result["assetProductVo"] = {
            field: product[field] for field in PRODUCT_FIELDS if field in product
        }
    return result


GROUP_FIELDS = (
    "id",
    "quotationGroupId",
    "quotationGroupName",
    "bankId",
    "department",
    "tntInstId",
    "version",
    "status",
    "processStatus",
    "gmtCreate",
    "gmtModified",
    "lastModifiedTime",
    "memo",
    "detailReason",
    "contactInformation",
    "contactMethod",
    "contactInfoList",
    "operationHistoryList",
)
CONTACT_FIELDS = ("emailAddress", "memo", "name")
GROUP_DETAIL = DetailSpec(
    path=("investment", "quote-groups"),
    action="get",
    kind=SETTINGS,
    title="physical quotation-group configuration version",
    endpoint="/queryQuotationDetail.json",
    method="POST",
    encoding=ENC_FORM,
    envelope=ENV_SUCCESS,
    container=("data",),
    tenant_field=False,
    identity=(
        IdentityOption(
            "quotation_group_row_id",
            "quotationGroupId",
            "Physical version-row id from native page/history; never "
            "business quotationGroupId.",
            echo="id",
        ),
    ),
    projection="quotation_group_detail",
    schema_version="quotation-group-row-detail-v1",
    table_columns=("id", "quotationGroupId", "version", "quotationGroupName", "status"),
    notes=(
        "Form POST sends only quotationGroupId with selected "
        "physical row.id; exact data.id echo required.",
        "Business quotationGroupId, physical id and native integer "
        "version are distinct; no latest/version lookup.",
        "Selected root version stays selected even when "
        "operationHistoryList contains newer versions.",
        "Contacts and curated history stay native arrays; selected "
        "root may also appear in history.",
        "Attachments, review/action plumbing are excluded and "
        "nonempty recursive history is unsupported.",
        "quote-groups list remains unsupported; this independent "
        "detail performs no implicit list acquisition.",
    ),
)


def _group_identity(row: dict[str, Any]) -> None:
    for field in ("id", "quotationGroupId"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise CliError(
                INVALID_RESPONSE, "quotation group has invalid native identity"
            )
    if row.get("tntInstId") != TENANT:
        raise CliError(INVALID_RESPONSE, "quotation group tenant contradicts scope")
    if type(row.get("version")) is not int:
        raise CliError(
            INVALID_RESPONSE, "quotation group version must be a native integer"
        )


def _project_group_row(row: dict[str, Any]) -> dict[str, Any]:
    _group_identity(row)
    result = {field: row[field] for field in GROUP_FIELDS if field in row}
    if "contactInfoList" in row and row["contactInfoList"] is not None:
        contacts = row["contactInfoList"]
        if not isinstance(contacts, list) or any(
            not isinstance(contact, dict) for contact in contacts
        ):
            raise CliError(
                INVALID_RESPONSE, "quotation group contacts must be an array of objects"
            )
        result["contactInfoList"] = [dict(contact) for contact in contacts]
    return result


def project_group_detail(row: dict[str, Any]) -> dict[str, Any]:
    result = _project_group_row(row)
    if "operationHistoryList" not in row or row["operationHistoryList"] is None:
        return result
    history = row["operationHistoryList"]
    if not isinstance(history, list) or any(
        not isinstance(entry, dict) for entry in history
    ):
        raise CliError(
            INVALID_RESPONSE, "quotation group history must be an array of objects"
        )
    seen: set[str] = set()
    projected = []
    for entry in history:
        item = _project_group_row(entry)
        if entry["quotationGroupId"] != row["quotationGroupId"] or entry["id"] in seen:
            raise CliError(
                INVALID_RESPONSE, "quotation group history identity/context conflict"
            )
        if entry["id"] == row["id"] and entry["version"] != row["version"]:
            raise CliError(
                INVALID_RESPONSE,
                "selected quotation group history version contradicts root",
            )
        seen.add(entry["id"])
        if (
            "operationHistoryList" in entry
            and entry["operationHistoryList"] is not None
        ):
            nested = entry["operationHistoryList"]
            if not isinstance(nested, list) or nested:
                raise CliError(
                    INVALID_RESPONSE, "recursive quotation group history is unsupported"
                )
        projected.append(item)
    result["operationHistoryList"] = projected
    return result


VERSIONED_GETTERS = (ASSET_DETAIL, GROUP_DETAIL)

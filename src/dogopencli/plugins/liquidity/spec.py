"""Liquidity leaf specifications: the declarative contract registry (issue #72).

Every shipped business leaf declares exactly one kind (runtimes | settings |
reference), its verified origin/method/path/encoding, exact request template,
native record container and reported-total paths, typed identity, offline
profile and retention series. Deferred leaves stay discoverable through
``DeferredLeaf`` with their evidence status and reason; they never become
placeholder commands. Evidence:
docs/research/general/2026-10-01-liquidity-live-probes.md.
"""

from dataclasses import dataclass, field
from typing import Any

# Mandatory kinds (issue #71).
RUNTIMES = "runtimes"
SETTINGS = "settings"
REFERENCE = "reference"
KINDS = (RUNTIMES, SETTINGS, REFERENCE)

# Envelope families observed on 2026-10-01.
ENV_SUCCESS = "success"  # {success: true, data: ...}
ENV_BASE_RESULT = "baseResult"  # {baseResult: {success: true, data: ...}}
ENV_RESULT_FLAG = "resultFlag"  # {resultFlag: true, result: {...}}
ENV_RESULT_SUCCESS = "resultSuccess"  # {success: true, result: {success: true, ...}}

# Pagination styles.
PAGE_OFFSET = "offset"  # rowStart/pageSize loop against a fixed reported total
PAGE_SINGLE = "single"  # one verified request returns the whole scoped set

# Offline profiles.
PROFILE_SNAPSHOT = "snapshot"  # settings/reference: one current capture per scope
PROFILE_HISTORY = "history"  # full current listing; captures retained by fetch time
PROFILE_DATED = "dated"  # business-window acquisition retained by window

# Wire encodings (EndpointContract.encoding; GET always serializes as query).
ENC_JSON = "json"
ENC_FORM = "form"

TENANT = "GUAPW3SG"
HOST = "iliquidity.alipay.com"
PAGE_SIZE = 10  # default for leaves without a larger verified request width

# Product retention cap per liquidity business leaf (ADR 0017): primary
# business records across that leaf's retained dates, captures and filter
# variants. A product policy, not a proven SQLite capacity limit.
RETENTION_CAP = 1_000_000


@dataclass(frozen=True)
class ScopeOption:
    """One verified scope parameter shared by refresh acquisition and queries.

    ``window`` marks the business-window dimension of a dated leaf: ``from``
    and ``to`` bound the retained coverage; ``both`` is a single-day window.
    Non-window options distinguish the source filter scope. ``repeat`` sends
    a JSON list; only the verified list shapes may be produced.
    """

    flag: str
    field: str
    summary: str
    required: bool = False
    choices: tuple[str, ...] = ()
    default: str | None = None
    date: bool = False
    repeat: bool = False
    window: str | None = None  # from | to | both
    verified: str = ""
    # Virtual options select a contract variant (e.g. a route or status set)
    # and shape the scope identity, but are never sent to the backend.
    virtual: bool = False
    # The verified wire shape is a single-element JSON list.
    list_of_one: bool = False
    # Value this spec binds for a virtual option in a variant leaf.
    match: str = ""
    # Verified compact HHmmss internally; the canonical public HH:mm:ss form
    # normalizes to it, without an inferred source timezone.
    time: bool = False
    # Canonical public flag when an Issue #127 rename moved the preferred
    # spelling away from the stable internal dest ``flag``; the dest-derived
    # flag stays accepted as a deprecated legacy alias.
    canonical_flag: str | None = None
    # Datetime options keep the native local ``YYYY-MM-DD HH:mm:ss`` string
    # internally; ``utc`` marks the verified-UTC rule-status semantics so
    # refresh hints reconstruct the preferred public instant form (#127).
    datetime_zone: str | None = None  # None | "utc" | "unknown"
    # Machine-readable occurrence bounds for repeat options (#127 T09/T11);
    # a wire list-of-one stays single-valued publicly.
    min_values: int | None = None
    max_values: int | None = None

    @property
    def public_flag(self) -> str:
        """Preferred public spelling for help, errors, and refresh hints."""
        if self.canonical_flag is not None:
            return self.canonical_flag
        return "--" + self.flag.replace("_", "-")

    @property
    def legacy_flags(self) -> tuple[str, ...]:
        """Deprecated spellings the Issue #127 rename replaced."""
        derived = "--" + self.flag.replace("_", "-")
        if self.canonical_flag is not None and self.canonical_flag != derived:
            return (derived,)
        return ()


@dataclass(frozen=True)
class ListSpec:
    """Verified list inquiry contract and offline behavior of one leaf."""

    path: tuple[str, ...]  # command words after `liquidity`, without `list`
    kind: str
    title: str
    endpoint: str
    method: str
    envelope: str
    container: tuple[str, ...]
    identity: tuple[str, ...]  # empty: no native key; preserve row occurrences
    encoding: str = ENC_JSON
    total: tuple[str, ...] | None = None
    pagination: str = PAGE_OFFSET
    profile: str = PROFILE_SNAPSHOT
    series_field: str | None = None  # business series time for dated records
    series_format: str | None = None  # verified native time format, read as a day
    template: dict[str, Any] = field(default_factory=dict)
    vo_field: str | None = None  # nested VO carried as one JSON string field
    scope_options: tuple[ScopeOption, ...] = ()
    # (flag, row field[, canonical flag]) local match; the optional third
    # element is the Issue #127 canonical spelling of a renamed filter.
    filters: tuple[tuple[str, ...], ...] = ()
    table_columns: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    # False for verified requests without pagination fields (metrics,
    # cash flows): the single response is the whole scoped set.
    paged_request: bool = True
    # Per-leaf request width, based on verified inquiry responses.
    page_size: int = PAGE_SIZE
    projection: str = ""
    total_checks: tuple[tuple[str, ...], ...] = ()
    require_inner_success: bool = False
    schema_version: str = ""  # nonempty versions isolate new projected caches

    @property
    def leaf(self) -> str:
        return " ".join((*self.path, "list"))

    @property
    def name(self) -> str:
        return "liquidity." + ".".join((*self.path, "list"))


@dataclass(frozen=True)
class IdentityOption:
    """One typed native identity parameter of a detail/history inquiry."""

    flag: str
    field: str  # native request field
    summary: str
    kind: str = "str"  # str | int
    echo: str | None = None  # response field that must repeat the value
    choices: tuple[str, ...] = ()
    virtual: bool = False  # cache/echo identity only; never sent to the backend


@dataclass(frozen=True)
class DetailSpec:
    """Verified native detail (or configuration history) inquiry contract."""

    path: tuple[str, ...]  # command words after `liquidity`, without action
    action: str  # get | history
    kind: str
    title: str
    endpoint: str
    method: str
    envelope: str
    container: tuple[str, ...]
    identity: tuple[IdentityOption, ...]
    encoding: str = ENC_JSON
    container_list: bool = False  # the detail payload is a list of records
    echo_list_field: str | None = None  # per-row echo field for list payloads
    list_leaf: tuple[str, ...] | None = None  # parent list path for hints
    table_columns: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    # Whether the verified request carries tntInstId. None derives it from
    # the method (every observed GET detail carries it); the two product
    # POST inquiries are the observed POST exceptions.
    tenant_field: bool | None = None
    template: dict[str, Any] = field(default_factory=dict)
    projection: str = ""
    schema_version: str = ""

    @property
    def sends_tenant(self) -> bool:
        return self.method == "GET" if self.tenant_field is None else self.tenant_field

    @property
    def leaf(self) -> str:
        return " ".join((*self.path, self.action))

    @property
    def name(self) -> str:
        return "liquidity." + ".".join((*self.path, self.action))


@dataclass(frozen=True)
class DeferredLeaf:
    """An audited leaf that stays unavailable, with its evidence reason."""

    path: tuple[str, ...]  # command words after `liquidity`, including action
    kind: str
    status: str
    reason: str

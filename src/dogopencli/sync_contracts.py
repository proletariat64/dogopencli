"""Leaf-owned durable acquisition declarations, independent of storage and CLI."""

from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import CliError


@dataclass(frozen=True)
class SyncTime:
    start_parameter: str
    end_parameter: str
    format: str = "date"
    timezone: str | None = None
    end_inclusive: bool | None = True
    max_days: int = 1
    overlap_days: int = 1
    partitionable: bool = False
    follow_supported: bool = False
    basis: str = "native query time"
    precision: str = "second"


@dataclass(frozen=True)
class SyncProfile:
    variant: str
    mode: str
    key_fields: tuple[str, ...]
    scope_parameters: tuple[str, ...]
    match: dict[str, Any] = field(default_factory=dict)
    present: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    time: SyncTime | None = None
    version_field: str | None = None
    version_kind: str | None = None
    unsupported_reason: str | None = None
    evidence: str = ""
    priority: int = 10
    allow_empty_key_components: bool = False
    native_defaults: dict[str, Any] = field(default_factory=dict)

    def accepts(self, parameters: dict[str, Any]) -> bool:
        values = {key.replace("_", "-"): value for key, value in parameters.items()}
        return (
            all(values.get(key) == value for key, value in self.match.items())
            and all(values.get(key) is not None for key in self.present)
            and all(values.get(key) is None for key in self.absent)
        )


def _invalid(message: str) -> CliError:
    return CliError("INVALID_LEAF", f"sync: {message}")


def _names(value: Any, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(x, str) or not x.strip() for x in value
    ):
        raise _invalid(f"{label} must contain nonempty names")
    if len(set(value)) != len(value) or (nonempty and not value):
        raise _invalid(f"{label} must contain unique native names")
    return tuple(value)


def profiles(manifest: dict[str, Any]) -> tuple[SyncProfile, ...]:
    """Return validated declarations; missing declarations never imply support."""
    declarations = manifest.get("sync")
    if declarations is None:
        return ()
    operation = manifest.get("operations", {}).get("list")
    if operation is None or not isinstance(declarations, list) or not declarations:
        raise _invalid(
            "declarations require an enumerable List and at least one variant"
        )
    definitions = {p["name"]: p for p in operation["parameters"]}
    result = []
    variants = set()
    allowed = set(SyncProfile.__dataclass_fields__)
    for declaration in declarations:
        if not isinstance(declaration, dict) or set(declaration) - allowed:
            raise _invalid("unknown profile entries")
        variant = declaration.get("variant")
        mode = declaration.get("mode")
        if not isinstance(variant, str) or not variant.strip() or variant in variants:
            raise _invalid("variant must be nonempty and unique")
        variants.add(variant)
        if mode not in {"settings", "runtime", "observation"}:
            raise _invalid("mode must be settings, runtime or observation")
        reason = declaration.get("unsupported_reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise _invalid("unsupported_reason must identify a concrete contract gap")
        keys = _names(
            declaration.get("key_fields", []), "key_fields", nonempty=reason is None
        )
        scopes = _names(declaration.get("scope_parameters", []), "scope_parameters")
        present = _names(declaration.get("present", []), "present")
        absent = _names(declaration.get("absent", []), "absent")
        if set(present) & set(absent):
            raise _invalid("a parameter cannot be both present and absent")
        defaults = declaration.get("parameters", {})
        native_defaults = declaration.get("native_defaults", {})
        match = declaration.get("match", {})
        if not all(
            isinstance(value, dict) for value in (defaults, native_defaults, match)
        ):
            raise _invalid("parameters and match must be objects")
        if (
            set(scopes)
            | set(present)
            | set(absent)
            | set(defaults)
            | set(native_defaults)
            | set(match)
        ) - definitions.keys():
            raise _invalid("profile refers to undeclared native parameters")
        for key, value in [*native_defaults.items(), *defaults.items(), *match.items()]:
            definition = definitions[key]
            values = value if definition.get("multiple") else [value]
            if not isinstance(values, list):
                raise _invalid(f"{key} requires a list")
            for item in values:
                kind = definition["type"]
                valid = (
                    (kind == "string" and isinstance(item, str))
                    or (kind == "integer" and type(item) is int)
                    or (kind == "boolean" and type(item) is bool)
                    or (kind == "number" and type(item) in {int, float})
                )
                if not valid or (
                    "choices" in definition and item not in definition["choices"]
                ):
                    raise _invalid(f"{key} has an invalid declared value")
        evidence = declaration.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise _invalid("evidence must describe the qualified acquisition contract")
        time = declaration.get("time")
        if time is not None:
            if (
                not isinstance(time, dict)
                or set(time) - SyncTime.__dataclass_fields__.keys()
            ):
                raise _invalid("unknown time declaration entries")
            if any(
                time.get(key) not in definitions
                for key in ("start_parameter", "end_parameter")
            ):
                raise _invalid("time bounds must be declared native parameters")
            if {time["start_parameter"], time["end_parameter"]} & set(scopes):
                raise _invalid("time windows cannot be record namespaces")
            try:
                time = SyncTime(**time)
            except TypeError as error:
                raise _invalid("invalid time declaration") from error
            if time.precision not in {"second", "millisecond"}:
                raise _invalid("unsupported native time precision")
            if time.format not in {
                "date",
                "compact_date",
                "datetime",
                "offset_datetime",
            }:
                raise _invalid("unsupported native time format")
            if any(
                type(getattr(time, key)) is not bool
                for key in ("partitionable", "follow_supported")
            ):
                raise _invalid("time policies must be booleans")
            if time.end_inclusive is not None and type(time.end_inclusive) is not bool:
                raise _invalid("end_inclusive must be boolean or unknown (null)")
            if time.partitionable and time.end_inclusive is None:
                raise _invalid("partitioning requires qualified boundary semantics")
            if (
                type(time.max_days) is not int
                or time.max_days < 1
                or type(time.overlap_days) is not int
                or time.overlap_days < 0
            ):
                raise _invalid("invalid chunk or overlap days")
            if time.timezone is not None:
                try:
                    ZoneInfo(time.timezone)
                except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
                    raise _invalid("timezone must be a qualified IANA zone") from error
            if time.follow_supported and (
                time.timezone is None or not time.partitionable
            ):
                raise _invalid("following requires qualified timezone and partitioning")
        version = declaration.get("version_field")
        version_kind = declaration.get("version_kind")
        if (version is None) != (version_kind is None) or (
            version is not None
            and (
                not isinstance(version, str)
                or not version.strip()
                or version_kind not in {"number", "datetime"}
            )
        ):
            raise _invalid(
                "source ordering requires a field and number/datetime representation"
            )
        priority = declaration.get("priority", 10)
        if type(priority) is not int or priority < 0:
            raise _invalid("priority must be a nonnegative integer")
        empty = declaration.get("allow_empty_key_components", False)
        if type(empty) is not bool:
            raise _invalid("allow_empty_key_components must be boolean")
        result.append(
            SyncProfile(
                variant,
                mode,
                keys,
                scopes,
                match,
                present,
                absent,
                defaults,
                time,
                version,
                version_kind,
                reason,
                evidence,
                priority,
                empty,
                native_defaults,
            )
        )
    return tuple(result)


def select_profile(manifest: dict[str, Any], parameters: dict[str, Any]) -> SyncProfile:
    """Select an explicit variant without guessing from timestamps or leaf names."""
    matches = [profile for profile in profiles(manifest) if profile.accepts(parameters)]
    if len(matches) != 1:
        raise CliError(
            "SYNC_UNSUPPORTED",
            "Select exactly one qualified sync variant using its native parameters",
        )
    profile = matches[0]
    if profile.unsupported_reason:
        raise CliError("SYNC_UNSUPPORTED", profile.unsupported_reason)
    return profile

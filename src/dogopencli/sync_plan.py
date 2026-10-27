"""Native time windows and coverage comparison for saved synchronization targets."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .errors import CliError
from .jsonutil import canonical


def _invalid(message):
    return CliError("INVALID_ARGUMENT", message, exit_code=2)


def parse_bound(value, policy):
    try:
        if policy.format in {"date", "compact_date"}:
            text = str(value)
            return datetime.strptime(
                text, "%Y%m%d" if len(text) == 8 else "%Y-%m-%d"
            ).date()
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            if policy.format == "offset_datetime":
                raise ValueError
            if policy.timezone:
                result = result.replace(tzinfo=ZoneInfo(policy.timezone))
        elif policy.timezone:
            result = result.astimezone(ZoneInfo(policy.timezone))
        return result
    except (ValueError, TypeError) as error:
        raise _invalid("Invalid native sync time boundary") from error


def format_bound(value, policy):
    if policy.format in {"date", "compact_date"}:
        return value.strftime(
            "%Y%m%d" if policy.format == "compact_date" else "%Y-%m-%d"
        )
    if policy.format == "datetime":
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value.isoformat(
        timespec="milliseconds" if policy.precision == "millisecond" else "seconds"
    )


def today_bounds(policy, cutoff):
    if not policy.follow_supported or not policy.timezone:
        raise CliError(
            "SYNC_UNSUPPORTED",
            "Native clock/boundaries are not qualified for today's automatic scope",
        )
    current = cutoff.astimezone(ZoneInfo(policy.timezone))
    if policy.format in {"date", "compact_date"}:
        return current.date(), current.date()
    return datetime.combine(current.date(), time.min, tzinfo=current.tzinfo), current


def windows(target, profile, cutoff, *, initial=False):
    """Yield one native chunk at a time; unknown boundaries remain indivisible."""
    policy = profile.time
    if policy is None:
        yield {}
        return
    start_key = policy.start_parameter.replace("-", "_")
    end_key = policy.end_parameter.replace("-", "_")
    parameters = target["parameters"]
    if start_key not in parameters or end_key not in parameters:
        raise _invalid("Both qualified native sync time boundaries are required")
    start = parse_bound(parameters[start_key], policy)
    end = parse_bound(parameters[end_key], policy)
    if target["follow"] and not initial:
        _, end = today_bounds(policy, cutoff)
    if start > end or (start == end and policy.end_inclusive is False):
        raise _invalid("Sync start must precede its end")
    if not policy.partitionable:
        yield {start_key: parameters[start_key], end_key: parameters[end_key]}
        return
    is_date = policy.format in {"date", "compact_date"}
    tick = (
        timedelta(days=1)
        if is_date
        else timedelta(milliseconds=1)
        if policy.precision == "millisecond"
        else timedelta(seconds=1)
    )
    stop = end + tick if policy.end_inclusive else end
    cursor = start
    while cursor < stop:
        if is_date:
            next_start = min(cursor + timedelta(days=policy.max_days), stop)
        else:
            next_start = min(
                datetime.combine(
                    cursor.date() + timedelta(days=policy.max_days),
                    time.min,
                    tzinfo=cursor.tzinfo,
                ),
                stop,
            )
        last = next_start - tick if policy.end_inclusive else next_start
        yield {
            start_key: format_bound(cursor, policy),
            end_key: format_bound(last, policy),
        }
        cursor = next_start


def coverage_identity(target):
    """Coverage must match acquisition filters, not merely durable row namespace."""
    parameters = dict(target["parameters"])
    time_policy = target["profile"].get("time")
    if time_policy:
        for key in (time_policy["start_parameter"], time_policy["end_parameter"]):
            parameters.pop(key.replace("-", "_"), None)
    return canonical(
        {
            "leaf": target["leaf_id"],
            "variant": target["variant"],
            "namespace": target["namespace"],
            "parameters": parameters,
            "profile": target["profile"],
            "adapter": target["adapter_sha256"],
            "manifest": target["manifest"],
        }
    )


def recent(chunk, profile, cutoff):
    policy = profile.time
    if policy is None:
        return True
    if not policy.timezone:
        return False
    end = parse_bound(chunk[policy.end_parameter.replace("-", "_")], policy)
    end_day = end if policy.format in {"date", "compact_date"} else end.date()
    return end_day >= cutoff.astimezone(ZoneInfo(policy.timezone)).date() - timedelta(
        days=policy.overlap_days
    )

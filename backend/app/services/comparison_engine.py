"""Pure deterministic response comparison, with bounded work and explicit uncertainty."""

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from app.core.redaction import REDACTED, Redactor
from app.schemas.comparison import ComparisonRules, child_pointer, pointer_tokens

ALGORITHM_VERSION = "pointer-v1"
MAX_DEPTH = 64
MAX_NODES = 50000
MAX_INPUT_BYTES = 2_200_000
MAX_DIFFERENCES = 500
MAX_VALUE_BYTES = 2048
CHANGE_TYPES = (
    "field_added",
    "field_removed",
    "value_changed",
    "type_changed",
    "array_changed",
    "status_changed",
    "header_added",
    "header_removed",
    "header_changed",
    "text_changed",
)
MISSING = object()


@dataclass
class Snapshot:
    status: int | None
    headers: dict
    body: Any
    kind: str
    error: dict | None = None


@dataclass
class EngineResult:
    comparison_status: str = "identical"
    differences: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(CHANGE_TYPES, 0)
    )


class LimitExceeded(Exception):
    pass


def check_budget(value):
    stack, nodes = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > MAX_DEPTH + 3 or nodes > MAX_NODES:
            raise LimitExceeded(
                "Input depth or node limit exceeded; comparison is incomplete."
            )
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
    if (
        len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())
        > MAX_INPUT_BYTES
    ):
        raise LimitExceeded("Input byte limit exceeded; comparison is incomplete.")


def value_type(value):
    if value is MISSING:
        return "missing"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def canonical(value):
    kind = value_type(value)
    if kind == "object":
        return (kind, tuple((k, canonical(value[k])) for k in sorted(value)))
    if kind == "array":
        return (kind, tuple(canonical(v) for v in value))
    if kind == "number":
        if not value:
            return (kind, 0, (0,), 0)
        sign, digits, exponent = Decimal(str(value)).as_tuple()
        # Strip trailing zeros without Decimal.normalize(), which rounds to context precision.
        digits = list(digits)
        while digits and digits[-1] == 0:
            digits.pop()
            exponent += 1
        return (kind, sign, tuple(digits), exponent)
    return (kind, value)


def masked(value):
    if isinstance(value, str):
        return REDACTED in value
    if isinstance(value, list):
        return any(masked(v) for v in value)
    if isinstance(value, dict):
        return any(masked(k) or masked(v) for k, v in value.items())
    return False


def safe_snapshot(snapshot: Snapshot) -> Snapshot:
    redactor = Redactor()
    # Normalize without merging duplicates into an ambiguous comma-delimited string.
    headers: dict[str, list[str]] = {}
    for key, value in snapshot.headers.items():
        headers.setdefault(key.lower(), []).extend(
            value if isinstance(value, list) else [value]
        )
    redactor.collect(headers)
    redactor.collect(snapshot.body)
    return Snapshot(
        snapshot.status,
        redactor.clean(headers),
        redactor.clean(snapshot.body),
        snapshot.kind,
        snapshot.error,
    )


def preview(value):
    if value is MISSING:
        return None, "Missing", False
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    truncated = len(text.encode()) > MAX_VALUE_BYTES
    return (
        (None if truncated else value),
        text[:500] + ("…" if len(text) > 500 else ""),
        truncated,
    )


def resolve(value, path):
    for token in pointer_tokens(path):
        if isinstance(value, dict):
            value = value.get(token, MISSING)
        elif isinstance(value, list) and (
            token == "0"
            or (token.isascii() and token.isdigit() and not token.startswith("0"))
        ):
            index = int(token)
            value = value[index] if index < len(value) else MISSING
        else:
            return MISSING
    return value


def compare_snapshots(
    original: Snapshot, replayed: Snapshot, rules: ComparisonRules
) -> EngineResult:
    output = EngineResult()
    notes: set[str] = set()
    partial = False
    try:
        check_budget([original.body, replayed.body, original.headers, replayed.headers])
        old, new = safe_snapshot(original), safe_snapshot(replayed)
        transport = {
            "timeout",
            "connection_error",
            "execution_interrupted",
            "not_executed",
            "session_deadline",
            "target_blocked",
        }
        if (
            old.status is None
            or new.status is None
            or any((s.error or {}).get("code") in transport for s in (old, new))
        ):
            output.comparison_status = "unavailable"
            output.notes = [
                "A complete HTTP response is unavailable. Inspect the original/replay execution error; no response differences were inferred."
            ]
            return output

        def emit(scope, path, change, a=MISSING, b=MISSING, types=None):
            if len(path.encode()) > 4096:
                raise LimitExceeded(
                    "Difference path length limit reached; comparison is incomplete."
                )
            if len(output.differences) >= MAX_DIFFERENCES:
                raise LimitExceeded(
                    "Difference limit reached; displayed counts are retained differences, not the full total."
                )
            av, ap, at = preview(a)
            bv, bp, bt = preview(b)
            output.differences.append(
                dict(
                    ordinal=len(output.differences),
                    scope=scope,
                    path=path,
                    change_type=change,
                    old_type=types[0] if types else value_type(a),
                    new_type=types[1] if types else value_type(b),
                    old_present=a is not MISSING,
                    new_present=b is not MISSING,
                    old_value=av,
                    new_value=bv,
                    old_preview=ap,
                    new_preview=bp,
                    old_value_truncated=at,
                    new_value_truncated=bt,
                )
            )
            output.counts[change] += 1

        def walk(a, b, path="", depth=0):
            nonlocal partial
            if path in rules.ignored_json_paths:
                return
            if depth > MAX_DEPTH:
                raise LimitExceeded(
                    "JSON depth limit reached; comparison is incomplete."
                )
            ak, bk = value_type(a), value_type(b)
            if a is MISSING:
                emit("body", path, "field_added", a, b)
            elif b is MISSING:
                emit("body", path, "field_removed", a, b)
            elif (isinstance(a, str) and masked(a)) or (
                isinstance(b, str) and masked(b)
            ):
                partial = True
                notes.add(
                    "Masked values are not compared; hidden contents cannot be inferred."
                )
            elif ak != bk:
                emit("body", path, "type_changed", a, b)
            elif ak == "object":
                for key in sorted(set(a) | set(b)):
                    walk(
                        a.get(key, MISSING),
                        b.get(key, MISSING),
                        child_pointer(path, key),
                        depth + 1,
                    )
            elif ak == "array":
                if path in rules.unordered_array_paths:
                    if masked(a) or masked(b):
                        partial = True
                        notes.add(
                            "An unordered array contains masked data and was not compared."
                        )
                    elif sorted((canonical(v) for v in a), key=repr) != sorted(
                        (canonical(v) for v in b), key=repr
                    ):
                        emit("body", path, "array_changed", a, b)
                else:
                    for index in range(max(len(a), len(b))):
                        walk(
                            a[index] if index < len(a) else MISSING,
                            b[index] if index < len(b) else MISSING,
                            child_pointer(path, index),
                            depth + 1,
                        )
            elif (canonical(a) != canonical(b)) if ak == "number" else (a != b):
                emit("body", path, "value_changed", a, b)

        if old.status != new.status:
            emit("status", "/status", "status_changed", old.status, new.status)
        for key in sorted(set(old.headers) | set(new.headers)):
            if key in rules.ignored_headers:
                continue
            a, b = old.headers.get(key, MISSING), new.headers.get(key, MISSING)
            if a is not MISSING and b is not MISSING and (masked(a) or masked(b)):
                partial = True
                notes.add("Masked header values are not compared.")
            elif a != b:
                emit(
                    "headers",
                    child_pointer("", key),
                    "header_added"
                    if a is MISSING
                    else "header_removed"
                    if b is MISSING
                    else "header_changed",
                    a,
                    b,
                )
        supported = {"json", "text", "empty"}
        if (
            old.error
            or new.error
            or old.kind not in supported
            or new.kind not in supported
        ):
            partial = True
            notes.add(
                "Body comparison unavailable: an unsupported, omitted, truncated, or failed capture is present. Only available status and headers were compared."
            )
        elif "" not in rules.ignored_json_paths:
            if old.kind != new.kind:
                emit(
                    "body",
                    "",
                    "type_changed",
                    MISSING if old.kind == "empty" else old.body,
                    MISSING if new.kind == "empty" else new.body,
                    (old.kind + "_body", new.kind + "_body"),
                )
            elif old.kind == "json":
                walk(old.body, new.body)
            elif old.kind == "text":
                if masked(old.body) or masked(new.body):
                    partial = True
                    notes.add("Masked text is not compared.")
                elif old.body != new.body:
                    emit("body", "", "text_changed", old.body, new.body)
        output.comparison_status = (
            "partial" if partial else "different" if output.differences else "identical"
        )
    except LimitExceeded as exc:
        output.comparison_status = "limited"
        notes.add(str(exc))
    except (ValueError, TypeError, RecursionError):
        output.comparison_status = "unavailable"
        output.differences = []
        output.counts = dict.fromkeys(CHANGE_TYPES, 0)
        notes.add("Stored input cannot be compared safely as supported JSON/text.")
    output.notes = sorted(notes)
    return output

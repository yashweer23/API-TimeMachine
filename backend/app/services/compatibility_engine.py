"""Deterministic contract checks and conservative heuristics over persisted evidence.

This is not an OpenAPI validator or a prediction of consumer behaviour. Explicit
contracts are checked against saved responses, even where Phase 3 ignored a path.
"""

from app.schemas.compatibility import EndpointPolicy
from app.schemas.comparison import (
    DEFAULT_IGNORED_HEADERS,
    child_pointer,
    pointer_tokens,
)
from app.services.comparison_engine import (
    MISSING,
    Snapshot,
    LimitExceeded,
    canonical,
    check_budget,
    masked,
    preview,
    resolve,
    safe_snapshot,
    value_type,
)

ENGINE_VERSION = "compatibility-v1"
MAX_FINDINGS = 600
CLASSES = ("confirmed_breaking", "potentially_breaking", "informational", "unassessed")
UNKNOWN = object()


def counts_for(findings):
    counts = {key: sum(f["classification"] == key for f in findings) for key in CLASSES}
    counts["high_critical"] = sum(
        f["severity"] in ("high", "critical") for f in findings
    )
    counts["findings"] = len(findings)
    return counts


def verdict_for(counts, incomplete=False):
    if counts.get("confirmed_breaking", 0):
        return "incompatible_with_configured_contract"
    if counts.get("potentially_breaking", 0):
        return "potential_compatibility_issues"
    if incomplete or counts.get("unassessed", 0):
        return "insufficient_evidence"
    return "compatible_under_configured_policy"


def under(path, parent):
    return path == parent or path.startswith(parent + "/")


def shape(value):
    kind = value_type(value)
    if kind == "object":
        return (kind, tuple((k, shape(v)) for k, v in sorted(value.items())))
    if kind == "array":
        return (kind, tuple(shape(v) for v in value))
    return kind


def observed(body, path):
    """A masked ancestor cannot prove that its child is absent."""
    value = body
    for token in pointer_tokens(path):
        if isinstance(value, str) and masked(value):
            return UNKNOWN
        value = resolve(value, child_pointer("", token))
        if value is MISSING:
            break
    return value


def matches_type(value, expected):
    if expected == "integer":
        return type(value) is int or (type(value) is float and value.is_integer())
    return value_type(value) == expected


def added_properties(old, new, path="", unordered=()):
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(new):
            p = child_pointer(path, key)
            if key not in old:
                yield p, new[key]
            else:
                yield from added_properties(old[key], new[key], p, unordered)
    elif isinstance(old, list) and isinstance(new, list) and path not in unordered:
        for index, (a, b) in enumerate(zip(old, new)):
            yield from added_properties(a, b, child_pointer(path, index), unordered)


def assess(
    original: Snapshot,
    replay: Snapshot,
    differences,
    comparison_status,
    rules,
    policy: EndpointPolicy | None,
):
    findings, used = [], set()

    def emit(
        rule,
        classification,
        severity,
        confidence,
        scope,
        path,
        change,
        title,
        explanation,
        action,
        a=MISSING,
        b=MISSING,
        diff=None,
        requirement=None,
        preexisting=False,
    ):
        if len(findings) >= MAX_FINDINGS - 1:
            raise LimitExceeded("Assessment finding limit reached.")
        if len(path.encode()) > 4096:
            raise LimitExceeded("Assessment path limit reached.")
        av, ap, at = preview(a)
        bv, bp, bt = preview(b)
        if diff:
            used.add(diff["ordinal"])
        findings.append(
            dict(
                difference_id=diff.get("id") if diff else None,
                ordinal=len(findings),
                scope=scope,
                path=path,
                change_type=change,
                classification=classification,
                severity=severity,
                confidence=confidence,
                title=title,
                explanation=explanation
                + (
                    " The recorded baseline also violates this requirement; this is not evidence of a newly introduced regression."
                    if preexisting
                    else ""
                ),
                recommended_action=action,
                rule_id=rule,
                evidence=dict(
                    old_present=a is not MISSING,
                    new_present=b is not MISSING,
                    old_value=av,
                    new_value=bv,
                    old_preview=ap,
                    new_preview=bp,
                    old_value_truncated=at,
                    new_value_truncated=bt,
                    requirement=requirement,
                    baseline_already_violated=preexisting,
                ),
            )
        )

    def gap(rule, explanation, scope="coverage", path=""):
        emit(
            rule,
            "unassessed",
            None,
            "low",
            scope,
            path,
            "evidence_gap",
            "Insufficient evidence",
            explanation,
            "Inspect the saved evidence, refine the contract, and capture/compare complete responses before drawing a compatibility conclusion.",
        )

    def relevant(scope, path):
        return next(
            (
                d
                for d in differences
                if d["scope"] == scope
                and (d["path"] == path or (scope == "body" and under(path, d["path"])))
            ),
            None,
        )

    try:
        check_budget([original.body, replay.body, original.headers, replay.headers])
        old, new = safe_snapshot(original), safe_snapshot(replay)
        if old.status is None or new.status is None:
            gap(
                "evidence.http_missing",
                "An original or replay HTTP response is missing. Transport/capture outcomes are not HTTP status changes.",
            )
            return findings
        body_available = (
            old.kind in ("json", "empty")
            and new.kind in ("json", "empty")
            and not old.error
            and not new.error
        )
        a_body = MISSING if old.kind == "empty" else old.body
        b_body = MISSING if new.kind == "empty" else new.body
        if comparison_status in ("partial", "limited", "unavailable"):
            gap(
                "evidence.comparison_incomplete",
                f"The source comparison is {comparison_status}; ignored, redacted, omitted or bounded evidence may hide changes.",
            )
        if policy:
            if (
                policy.expected_status_codes
                and new.status not in policy.expected_status_codes
            ):
                emit(
                    "contract.status",
                    "confirmed_breaking",
                    "high" if new.status >= 400 else "medium",
                    "high",
                    "status",
                    "/status",
                    "status_changed",
                    "Status violates the declared contract",
                    "The replay status is outside the explicitly permitted successful status codes.",
                    "Restore a permitted status or revise the contract with consumers.",
                    old.status,
                    new.status,
                    relevant("status", "/status"),
                    policy.expected_status_codes,
                    old.status not in policy.expected_status_codes,
                )
            for name in policy.required_headers:
                if name not in new.headers:
                    emit(
                        "contract.required_header",
                        "confirmed_breaking",
                        "high",
                        "high",
                        "headers",
                        child_pointer("", name),
                        "header_removed",
                        "Required response header is absent",
                        "The declared required header is absent in the saved replay response.",
                        "Restore the required header and verify affected clients.",
                        old.headers.get(name, MISSING),
                        MISSING,
                        relevant("headers", child_pointer("", name)),
                        name,
                        name not in old.headers,
                    )
            if policy.allowed_content_types:

                def allowed(headers):
                    values = headers.get("content-type", [])
                    return bool(values) and all(
                        v.split(";")[0].strip().lower() in policy.allowed_content_types
                        for v in values
                    )

                media = new.headers.get("content-type", MISSING)
                if media is not MISSING and masked(media):
                    gap(
                        "evidence.content_type_masked",
                        "The content type is redacted and cannot be checked.",
                        "headers",
                        "/content-type",
                    )
                elif not allowed(new.headers):
                    emit(
                        "contract.content_type",
                        "confirmed_breaking",
                        "medium",
                        "high",
                        "headers",
                        "/content-type",
                        "header_changed",
                        "Content type violates the declared contract",
                        "The replay content type is missing or outside the explicit media type allowlist; charset parameters are ignored.",
                        "Return a permitted media type or explicitly update the contract.",
                        old.headers.get("content-type", MISSING),
                        media,
                        relevant("headers", "/content-type"),
                        policy.allowed_content_types,
                        not allowed(old.headers),
                    )
            body_rules = (
                policy.required_json_paths
                or policy.expected_types
                or policy.allow_additional_fields is False
            )
            if body_rules and not body_available:
                gap(
                    "evidence.contract_body_unavailable",
                    "JSON contract checks require complete JSON or a known empty response; text, omitted bodies and capture errors cannot prove JSON field violations.",
                    "body",
                )
            if body_available:
                for path in policy.required_json_paths:
                    a, b = observed(a_body, path), observed(b_body, path)
                    if b is UNKNOWN:
                        gap(
                            "evidence.required_path_masked",
                            "A redacted ancestor prevents checking this required path.",
                            "body",
                            path,
                        )
                    elif b is MISSING:
                        emit(
                            "contract.required_path",
                            "confirmed_breaking",
                            "critical" if path == "" else "high",
                            "high",
                            "body",
                            path,
                            "field_removed",
                            "Required JSON path is absent",
                            "The replay response does not contain an explicitly required JSON path.",
                            "Restore this path or coordinate a contract version change with consumers.",
                            MISSING if a is UNKNOWN else a,
                            b,
                            relevant("body", path),
                            path,
                            a is MISSING,
                        )
                for path, expected in policy.expected_types.items():
                    a, b = observed(a_body, path), observed(b_body, path)
                    if b is UNKNOWN or (
                        b is not MISSING and isinstance(b, str) and masked(b)
                    ):
                        gap(
                            "evidence.type_masked",
                            "A redacted value or ancestor prevents checking the declared type.",
                            "body",
                            path,
                        )
                    elif b is not MISSING and not matches_type(b, expected):
                        emit(
                            "contract.type",
                            "confirmed_breaking",
                            "critical" if path == "" else "high",
                            "high",
                            "body",
                            path,
                            "type_changed",
                            "JSON type violates the declared contract",
                            f"The replay value must have the explicitly declared type {expected}. Optional paths are checked only when present.",
                            "Restore the declared type; do not silently coerce consumer data.",
                            MISSING if a is UNKNOWN else a,
                            b,
                            relevant("body", path),
                            expected,
                            a is not MISSING
                            and a is not UNKNOWN
                            and not masked(a)
                            and not matches_type(a, expected),
                        )
                if policy.allow_additional_fields is False:
                    for array_path in rules.unordered_array_paths:
                        av, bv = (
                            observed(a_body, array_path),
                            observed(b_body, array_path),
                        )
                        if (
                            isinstance(av, list)
                            and isinstance(bv, list)
                            and sorted((canonical(v) for v in av), key=repr)
                            != sorted((canonical(v) for v in bv), key=repr)
                        ):
                            gap(
                                "evidence.unordered_additional_fields",
                                "Additional-property checks inside a changed unordered array need item identity; index-based matches would invent evidence.",
                                "body",
                                array_path,
                            )
                    for path, b in added_properties(
                        a_body, b_body, unordered=rules.unordered_array_paths
                    ):
                        emit(
                            "contract.additional_field",
                            "confirmed_breaking",
                            "medium",
                            "high",
                            "body",
                            path,
                            "field_added",
                            "New property is prohibited by policy",
                            "This object property was added relative to the recorded baseline, while the endpoint explicitly prohibits additional fields.",
                            "Remove the added property or explicitly permit additions after reviewing consumers.",
                            MISSING,
                            b,
                            relevant("body", path),
                            False,
                        )
        if new.status >= 400 and not any(
            f["rule_id"] == "contract.status" for f in findings
        ):
            emit(
                "heuristic.error_status",
                "potentially_breaking",
                "high",
                "medium",
                "status",
                "/status",
                "status_changed",
                "Replay returned an HTTP error",
                "An HTTP error may interrupt consumers, but no supplied successful-status contract proves a violation.",
                "Investigate the HTTP error and specify expected successful statuses.",
                old.status,
                new.status,
                relevant("status", "/status"),
                preexisting=old.status >= 400,
            )
        # Phase 3 ignores are not evidence of permission. Assess their coverage explicitly.
        if body_available:
            for path in rules.ignored_json_paths:
                a, b = observed(a_body, path), observed(b_body, path)
                if a is UNKNOWN or b is UNKNOWN:
                    gap(
                        "evidence.ignored_path",
                        "A comparison ignore hides redacted evidence at this path.",
                        "body",
                        path,
                    )
                elif a is MISSING and b is MISSING:
                    continue
                elif (
                    a is MISSING
                    or b is MISSING
                    or masked(a)
                    or masked(b)
                    or canonical(a) != canonical(b)
                ):
                    dynamic = policy and any(
                        under(path, p) for p in policy.dynamic_json_paths
                    )
                    if (
                        dynamic
                        and a is not MISSING
                        and b is not MISSING
                        and not masked(a)
                        and not masked(b)
                        and shape(a) == shape(b)
                    ):
                        emit(
                            "policy.dynamic_value",
                            "informational",
                            "low",
                            "high",
                            "body",
                            path,
                            "value_changed",
                            "Dynamic value change is permitted",
                            "Only values changed under an explicitly dynamic path; structure and types are unchanged.",
                            "No action under this policy; review whether the dynamic-path permission remains appropriate.",
                            a,
                            b,
                            requirement=path,
                        )
                    else:
                        gap(
                            "evidence.ignored_path",
                            "A changed JSON path was excluded by comparison rules. A comparison ignore does not establish consumer compatibility.",
                            "body",
                            path,
                        )
        for name in rules.ignored_headers:
            if name not in DEFAULT_IGNORED_HEADERS and old.headers.get(
                name, MISSING
            ) != new.headers.get(name, MISSING):
                gap(
                    "evidence.ignored_header",
                    "A changed header was excluded by user comparison rules; its semantics were not assessed.",
                    "headers",
                    child_pointer("", name),
                )
        for d in differences:
            if d["ordinal"] in used:
                continue
            scope, path, change = d["scope"], d["path"], d["change_type"]
            a = (
                resolve(a_body, path)
                if scope == "body" and old.kind == "json"
                else old.status
                if scope == "status"
                else resolve(old.headers, path)
                if scope == "headers"
                else old.body
            )
            b = (
                resolve(b_body, path)
                if scope == "body" and new.kind == "json"
                else new.status
                if scope == "status"
                else resolve(new.headers, path)
                if scope == "headers"
                else new.body
            )
            if not d["old_present"]:
                a = MISSING
            if not d["new_present"]:
                b = MISSING
            cls, sev, conf, rule = "unassessed", None, "low", "default.unassessed"
            title, explanation = (
                "Change needs consumer context",
                "No supplied contract or supported rule determines whether consumers depend on this changed value.",
            )
            action = "Review the Phase 3 difference with consumers and declare the relevant requirements."
            requirement = None
            if (
                change == "status_changed"
                and policy
                and b in policy.expected_status_codes
            ):
                cls, sev, conf, rule = (
                    "informational",
                    "low",
                    "high",
                    "policy.allowed_status",
                )
                title, explanation = (
                    "New status is explicitly permitted",
                    "The replay status is in the declared successful-status allowlist.",
                )
                requirement = policy.expected_status_codes
            elif (
                change == "header_changed"
                and path == "/content-type"
                and policy
                and policy.allowed_content_types
                and all(
                    v.split(";")[0].strip().lower() in policy.allowed_content_types
                    for v in new.headers.get("content-type", [])
                )
            ):
                cls, sev, conf, rule = (
                    "informational",
                    "low",
                    "high",
                    "policy.allowed_content_type",
                )
                title, explanation = (
                    "New content type is explicitly permitted",
                    "The replay media type is in the declared allowlist.",
                )
                requirement = policy.allowed_content_types
            elif (
                change == "value_changed"
                and policy
                and any(under(path, p) for p in policy.dynamic_json_paths)
            ):
                cls, sev, conf, rule = (
                    "informational",
                    "low",
                    "high",
                    "policy.dynamic_value",
                )
                title, explanation = (
                    "Dynamic value change is permitted",
                    "An explicit policy allows value changes at this path; removals and type changes are not exempt.",
                )
                requirement = next(
                    p for p in policy.dynamic_json_paths if under(path, p)
                )
            elif change in (
                "field_removed",
                "type_changed",
                "array_changed",
                "header_removed",
            ) or (scope == "headers" and path == "/content-type"):
                cls, sev, conf, rule = (
                    "potentially_breaking",
                    "high" if change == "type_changed" else "medium",
                    "medium"
                    if scope == "body" and change != "array_changed"
                    else "low",
                    "heuristic." + change,
                )
                title, explanation = (
                    "Structural change may affect consumers",
                    "A removal, type, array membership or media-type change can affect clients, but no explicit requirement proves breakage.",
                )
            elif change == "field_added" and isinstance(
                resolve(old.body, path.rsplit("/", 1)[0]), dict
            ):
                cls, sev, conf, rule = (
                    "informational",
                    "low",
                    "high"
                    if policy and policy.allow_additional_fields is True
                    else "low",
                    "policy.additional_allowed"
                    if policy and policy.allow_additional_fields is True
                    else "default.field_added",
                )
                title, explanation = (
                    "Object property was added",
                    "Additional object properties are explicitly allowed."
                    if conf == "high"
                    else "An addition is informational by default; strict consumers may still reject it. No strict-consumer contract was supplied.",
                )
                requirement = True if conf == "high" else None
            elif change == "header_added" or (
                scope == "headers"
                and path == "/content-length"
                and change == "header_changed"
            ):
                cls, sev, conf, rule = (
                    "informational",
                    "low",
                    "low",
                    "default.header_metadata",
                )
                title, explanation = (
                    "Response metadata changed",
                    "An added header or content-length update is informational by default; specialized consumers may impose additional requirements.",
                )
            emit(
                rule,
                cls,
                sev,
                conf,
                scope,
                path,
                change,
                title,
                explanation,
                action,
                a,
                b,
                d,
                requirement,
            )
    except LimitExceeded:
        # Reserve one slot for a coverage finding; never call a bounded assessment complete.
        findings.append(
            dict(
                difference_id=None,
                ordinal=len(findings),
                scope="coverage",
                path="",
                change_type="evidence_gap",
                classification="unassessed",
                severity=None,
                confidence="low",
                title="Assessment limit reached",
                explanation="The bounded assessment could not inspect all evidence. Counts include retained findings only.",
                recommended_action="Narrow the response or contract and capture/compare again.",
                rule_id="evidence.assessment_limit",
                evidence={},
            )
        )
    return findings

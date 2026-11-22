import json
import pytest
from pydantic import ValidationError
from app.schemas.compatibility import EndpointPolicy, PolicyBundle, fingerprint
from app.schemas.comparison import ComparisonRules
from app.services.comparison_engine import Snapshot, compare_snapshots
from app.services.compatibility_engine import (
    assess,
    counts_for,
    verdict_for,
    MAX_FINDINGS,
)


def analyze(
    old,
    new,
    policy=None,
    *,
    old_status=200,
    status=200,
    old_headers=None,
    headers=None,
    rules=None,
    kind="json",
    error=None,
):
    a = Snapshot(old_status, old_headers or {}, old, "json")
    b = Snapshot(status, headers or {}, new, kind, error)
    rules = rules or ComparisonRules()
    diff = compare_snapshots(a, b, rules)
    p = EndpointPolicy(endpoint_path="/users", **policy) if policy is not None else None
    return assess(a, b, diff.differences, diff.comparison_status, rules, p)


def select_rule(findings, rule):
    return [f for f in findings if f["rule_id"] == rule]


@pytest.mark.parametrize(
    "policy,old,new,rule,cls,severity,confidence",
    [
        (
            {"required_json_paths": ["/id"]},
            {"id": 1},
            {},
            "contract.required_path",
            "confirmed_breaking",
            "high",
            "high",
        ),
        (
            {"expected_types": {"/id": "integer"}},
            {"id": 1},
            {"id": "1"},
            "contract.type",
            "confirmed_breaking",
            "high",
            "high",
        ),
        (
            {"expected_types": {"": "object"}},
            {"id": 1},
            [],
            "contract.type",
            "confirmed_breaking",
            "critical",
            "high",
        ),
        (
            {"allow_additional_fields": False},
            {},
            {"x": 1},
            "contract.additional_field",
            "confirmed_breaking",
            "medium",
            "high",
        ),
        (
            {"allow_additional_fields": True},
            {},
            {"x": 1},
            "policy.additional_allowed",
            "informational",
            "low",
            "high",
        ),
        (
            {"dynamic_json_paths": ["/time"]},
            {"time": "a"},
            {"time": "b"},
            "policy.dynamic_value",
            "informational",
            "low",
            "high",
        ),
        (
            None,
            {"x": 1},
            {},
            "heuristic.field_removed",
            "potentially_breaking",
            "medium",
            "medium",
        ),
        (
            None,
            {"x": 1},
            {"x": "1"},
            "heuristic.type_changed",
            "potentially_breaking",
            "high",
            "medium",
        ),
        (None, {}, {"x": 1}, "default.field_added", "informational", "low", "low"),
        (None, {"x": 1}, {"x": 2}, "default.unassessed", "unassessed", None, "low"),
        (
            None,
            {"x": False},
            {"x": True},
            "default.unassessed",
            "unassessed",
            None,
            "low",
        ),
    ],
)
def test_rules_and_templates(policy, old, new, rule, cls, severity, confidence):
    findings = analyze(old, new, policy)
    f = select_rule(findings, rule)[0]
    assert (f["classification"], f["severity"], f["confidence"]) == (
        cls,
        severity,
        confidence,
    )
    assert f["title"] and f["explanation"] and f["recommended_action"]
    assert findings == analyze(old, new, policy)


@pytest.mark.parametrize(
    "policy,old,new",
    [
        ({"required_json_paths": ["/x"]}, {"x": None}, {"x": None}),
        ({"expected_types": {"/x": "integer"}}, {"x": 1}, {"x": 1.0}),
        ({"expected_types": {"/optional": "string"}}, {}, {}),
        ({"allow_additional_fields": False}, {"x": 1}, {"x": 1}),
        ({"expected_status_codes": [200]}, {}, {}),
    ],
)
def test_contract_non_triggers(policy, old, new):
    assert not analyze(old, new, policy)


@pytest.mark.parametrize(
    "expected,value,violation",
    [
        ("integer", True, True),
        ("number", False, True),
        ("boolean", True, False),
        ("null", None, False),
        ("integer", 1.5, True),
        ("integer", 2.0, False),
        ("number", 2, False),
        ("object", [], True),
        ("array", [], False),
        ("string", "a", False),
    ],
)
def test_types(expected, value, violation):
    findings = analyze({"x": value}, {"x": value}, {"expected_types": {"/x": expected}})
    assert bool(select_rule(findings, "contract.type")) == violation
    if violation:
        assert findings[0]["evidence"]["baseline_already_violated"]


@pytest.mark.parametrize(
    "status,policy,rule,classification",
    [
        (201, None, "default.unassessed", "unassessed"),
        (
            201,
            {"expected_status_codes": [200]},
            "contract.status",
            "confirmed_breaking",
        ),
        (
            201,
            {"expected_status_codes": [200, 201]},
            "policy.allowed_status",
            "informational",
        ),
        (500, None, "heuristic.error_status", "potentially_breaking"),
        (
            500,
            {"expected_status_codes": [200]},
            "contract.status",
            "confirmed_breaking",
        ),
    ],
)
def test_statuses(status, policy, rule, classification):
    f = select_rule(analyze({}, {}, policy, status=status), rule)[0]
    assert f["classification"] == classification


def test_header_and_media_rules():
    f = analyze(
        {}, {}, {"required_headers": ["x-schema"]}, old_headers={"X-Schema": "v1"}
    )
    assert select_rule(f, "contract.required_header")[0]["evidence"]["old_value"] == [
        "v1"
    ]
    f = analyze(
        {},
        {},
        {"allowed_content_types": ["application/json"]},
        headers={"Content-Type": "text/plain"},
    )
    assert select_rule(f, "contract.content_type")
    f = analyze(
        {},
        {},
        {"allowed_content_types": ["application/json"]},
        old_headers={"Content-Type": "application/json"},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert select_rule(f, "policy.allowed_content_type")


def test_precedence_dynamic_never_hides_type_or_removal_and_contract_overrides_ignore():
    policy = {
        "dynamic_json_paths": ["/x"],
        "required_json_paths": ["/x"],
        "expected_types": {"/x": "string"},
    }
    f = analyze(
        {"x": "a"}, {"x": 1}, policy, rules=ComparisonRules(ignored_json_paths=["/x"])
    )
    assert select_rule(f, "contract.type") and not select_rule(
        f, "policy.dynamic_value"
    )
    f = analyze({"x": "a"}, {}, policy)
    assert select_rule(f, "contract.required_path") and not select_rule(
        f, "policy.dynamic_value"
    )
    f = analyze(
        {},
        {"extra": 1},
        {"allow_additional_fields": False},
        rules=ComparisonRules(ignored_json_paths=["/extra"]),
    )
    assert select_rule(f, "contract.additional_field")


def test_ignored_dynamic_value_permitted_but_structural_ignore_incomplete():
    rules = ComparisonRules(ignored_json_paths=["/x"])
    f = analyze({"x": 1}, {"x": 2}, {"dynamic_json_paths": ["/x"]}, rules=rules)
    assert verdict_for(counts_for(f)) == "compatible_under_configured_policy"
    assert select_rule(f, "policy.dynamic_value")
    for new in ({"x": "2"}, {}, {"x": {"more": 1}}):
        f = analyze({"x": 1}, new, {"dynamic_json_paths": ["/x"]}, rules=rules)
        assert verdict_for(counts_for(f)) == "insufficient_evidence"
    f = analyze({"x": 1}, {"x": 2}, rules=rules)
    assert select_rule(f, "evidence.ignored_path")
    f = analyze(
        {},
        {},
        old_headers={"x-special": "a"},
        headers={"x-special": "b"},
        rules=ComparisonRules(ignored_headers=["x-special"]),
    )
    assert select_rule(f, "evidence.ignored_header")


def test_missing_masked_unsupported_and_capture_errors_are_unassessed():
    for kwargs in (
        {"status": None},
        {"kind": "omitted", "error": {"code": "response_too_large"}},
        {"kind": "text"},
    ):
        f = analyze({"id": 1}, {}, {"required_json_paths": ["/id"]}, **kwargs)
        assert not any(x["classification"] == "confirmed_breaking" for x in f)
        assert any(x["classification"] == "unassessed" for x in f)
    f = analyze(
        {"secret": {"id": 1}},
        {"secret": "[REDACTED]"},
        {
            "required_json_paths": ["/secret/id"],
            "expected_types": {"/secret": "object"},
        },
    )
    assert not any(x["classification"] == "confirmed_breaking" for x in f)
    assert select_rule(f, "evidence.required_path_masked") and select_rule(
        f, "evidence.type_masked"
    )


def test_safe_previews_arrays_and_limits():
    f = analyze({"payload": "x" * 4000}, {"payload": "y" * 4000})[0]
    assert f["evidence"]["old_value_truncated"] and f["evidence"]["old_value"] is None
    f = analyze({"password": "abcde"}, {"password": "vwxyz"})
    assert "abcde" not in json.dumps(f) and "vwxyz" not in json.dumps(f)
    f = analyze({"x": [1]}, {"x": [1, 2]}, {"allow_additional_fields": False})
    assert not select_rule(f, "contract.additional_field")
    f = analyze(
        {"x": [1, 2]},
        {"x": [1, 3]},
        rules=ComparisonRules(unordered_array_paths=["/x"]),
    )
    assert select_rule(f, "heuristic.array_changed")
    f = analyze(
        {}, {str(i): i for i in range(1000)}, {"allow_additional_fields": False}
    )
    assert len(f) <= MAX_FINDINGS and select_rule(f, "evidence.assessment_limit")
    assert any(x["classification"] == "unassessed" for x in f)


def test_unknown_change_and_preexisting_contract():
    f = assess(
        Snapshot(200, {}, {}, "json"),
        Snapshot(200, {}, {}, "json"),
        [
            dict(
                ordinal=0,
                scope="body",
                path="",
                change_type="future_change",
                old_present=True,
                new_present=True,
            )
        ],
        "different",
        ComparisonRules(),
        None,
    )
    assert f[0]["classification"] == "unassessed"
    f = analyze({}, {}, {"required_json_paths": ["/x"]})
    assert (
        f[0]["evidence"]["baseline_already_violated"]
        and "not evidence of a newly" in f[0]["explanation"]
    )


@pytest.mark.parametrize(
    "data",
    [
        {"required_json_paths": ["$.a"]},
        {"expected_types": {"/x~2": "string"}},
        {"expected_types": {"/x": "float"}},
        {"expected_status_codes": [500]},
        {"expected_status_codes": [True]},
        {"expected_status_codes": ["200"]},
        {"required_headers": ["x bad"]},
        {"allowed_content_types": ["application/*"]},
        {"allowed_content_types": ["text/html; charset=utf8"]},
        {"endpoint_path": "https://evil.test"},
        {"random": True},
        {"dynamic_json_paths": ["/" + "a" * 2050]},
    ],
)
def test_policy_validation(data):
    with pytest.raises(ValidationError):
        EndpointPolicy.model_validate({"endpoint_path": "/users", **data})


def test_canonical_policy_and_duplicate_rejection():
    a = PolicyBundle.model_validate(
        {
            "endpoints": [
                {
                    "endpoint_path": "/x",
                    "required_headers": ["X-A", "x-a"],
                    "expected_status_codes": [201, 200, 201],
                }
            ]
        }
    )
    b = PolicyBundle.model_validate(
        {
            "endpoints": [
                {
                    "endpoint_path": "/x",
                    "required_headers": ["x-a"],
                    "expected_status_codes": [200, 201],
                }
            ]
        }
    )
    assert fingerprint(a.model_dump()) == fingerprint(b.model_dump())
    with pytest.raises(ValidationError):
        PolicyBundle(endpoints=a.endpoints + a.endpoints)


@pytest.mark.parametrize(
    "counts,incomplete,expected",
    [
        ({}, False, "compatible_under_configured_policy"),
        ({}, True, "insufficient_evidence"),
        ({"unassessed": 1}, False, "insufficient_evidence"),
        (
            {"potentially_breaking": 1, "unassessed": 1},
            False,
            "potential_compatibility_issues",
        ),
        (
            {"confirmed_breaking": 1, "potentially_breaking": 1, "unassessed": 1},
            True,
            "incompatible_with_configured_contract",
        ),
    ],
)
def test_verdict_precedence(counts, incomplete, expected):
    assert verdict_for(counts, incomplete) == expected


def test_additional_properties_do_not_invent_identity_for_unordered_arrays():
    rules = ComparisonRules(unordered_array_paths=["/items"])
    old = {"items": [{"a": 1}, {"b": 2}]}
    new = {"items": [{"b": 2}, {"a": 1}]}
    f = analyze(old, new, {"allow_additional_fields": False}, rules=rules)
    assert not f
    changed = {"items": [{"b": 2, "c": 3}, {"a": 1}]}
    f = analyze(old, changed, {"allow_additional_fields": False}, rules=rules)
    assert not select_rule(f, "contract.additional_field")
    assert select_rule(f, "evidence.unordered_additional_fields")

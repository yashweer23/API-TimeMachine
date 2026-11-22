import copy
import pytest
from app.schemas.comparison import ComparisonRules
from app.services.comparison_engine import Snapshot, compare_snapshots, MAX_DIFFERENCES


def compare(a, b, **rules):
    return compare_snapshots(
        Snapshot(200, {}, a, "json"),
        Snapshot(200, {}, b, "json"),
        ComparisonRules(**rules),
    )


@pytest.mark.parametrize(
    "a,b,changes",
    [
        ({"a": 1, "b": True}, {"b": True, "a": 1.0}, []),
        ({}, {"x": None}, [("/x", "field_added")]),
        ({"x": None}, {}, [("/x", "field_removed")]),
        ({"x": 1}, {"x": "1"}, [("/x", "type_changed")]),
        ({"x": True}, {"x": 1}, [("/x", "type_changed")]),
        (None, "", [("", "type_changed")]),
        ([], {}, [("", "type_changed")]),
        ({"x": None}, {"x": []}, [("/x", "type_changed")]),
        (
            {"a": {"city": "Hyderabad"}},
            {"a": {"city": "Bangalore"}},
            [("/a/city", "value_changed")],
        ),
        (
            [["a", {"x": 1}]],
            [["a", {"x": 2}, None]],
            [("/0/1/x", "value_changed"), ("/0/2", "field_added")],
        ),
        ([1, 2], [2, 1], [("/0", "value_changed"), ("/1", "value_changed")]),
        ([1, 2], [1], [("/1", "field_removed")]),
        ({"a": {"nested": 1}}, {"a": False}, [("/a", "type_changed")]),
        (
            {"a/b": {"~x": 1}, "": 1},
            {"a/b": {"~x": 2}, "": 2},
            [("/", "value_changed"), ("/a~1b/~0x", "value_changed")],
        ),
    ],
)
def test_deep_json(a, b, changes):
    before = copy.deepcopy([a, b])
    result = compare(a, b)
    assert [(d["path"], d["change_type"]) for d in result.differences] == changes
    assert [a, b] == before
    assert result.comparison_status == ("different" if changes else "identical")


def test_presence_and_null():
    d = compare({}, {"x": None}).differences[0]
    assert d["old_present"] is False and d["new_present"] is True
    assert d["old_value"] is None and d["new_value"] is None
    assert d["old_type"] == "missing" and d["new_type"] == "null"


def test_ignore_exact_subtree_and_escaped_keys():
    assert (
        compare(
            {"a": {"x": 1}, "a/b": 2},
            {"a": {"x": 3}, "a/b": 4},
            ignored_json_paths=["/a", "/a~1b"],
        ).comparison_status
        == "identical"
    )


def test_unordered_array_multiset_and_equivalent_numbers():
    assert (
        compare(
            [{"n": 1}, 2, 2], [2, {"n": 1.0}, 2.0], unordered_array_paths=[""]
        ).comparison_status
        == "identical"
    )
    result = compare([1, 1], [1, 2], unordered_array_paths=[""])
    assert [d["change_type"] for d in result.differences] == ["array_changed"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ignored_json_paths": ["$.x"]},
        {"ignored_json_paths": ["/bad~escape"]},
        {"ignored_headers": ["Bad Header"]},
        {"ignored_json_paths": ["/a/0/x"], "unordered_array_paths": ["/a"]},
        {"unordered_array_paths": ["/a", "/a/0"]},
        {"ignored_json_paths": ["/" * 66]},
    ],
)
def test_invalid_rules(kwargs):
    with pytest.raises(ValueError):
        ComparisonRules(**kwargs)


def test_rule_fingerprint_is_canonical():
    assert (
        ComparisonRules(ignored_headers=["X-B", "X-A", "x-a"]).fingerprint()
        == ComparisonRules(ignored_headers=["x-a", "x-b"]).fingerprint()
    )
    rules = ComparisonRules()
    assert rules.fingerprint() == ComparisonRules(**rules.model_dump()).fingerprint()


def test_status_and_headers_with_repeated_values():
    a = Snapshot(
        200,
        {
            "Date": "yesterday",
            "Content-Type": "application/json",
            "X-Old": "a",
            "X-Multi": ["a", "b"],
        },
        {},
        "json",
    )
    b = Snapshot(
        404,
        {
            "date": "today",
            "content-type": "text/plain",
            "X-New": "b",
            "x-multi": ["a", "c"],
        },
        {},
        "json",
    )
    result = compare_snapshots(a, b, ComparisonRules())
    assert [d["change_type"] for d in result.differences] == [
        "status_changed",
        "header_changed",
        "header_changed",
        "header_added",
        "header_removed",
    ]
    assert result.differences[2]["old_value"] == ["a", "b"]
    assert (
        compare_snapshots(
            Snapshot(200, {"X-A": "a"}, None, "empty"),
            Snapshot(200, {"x-a": ["a"]}, None, "empty"),
            ComparisonRules(),
        ).comparison_status
        == "identical"
    )


@pytest.mark.parametrize(
    "kind,a,b,change",
    [
        ("text", "<a/>", "<b/>", "text_changed"),
        ("text", '{"n":1}', '{"n":2}', "text_changed"),
        ("empty", None, None, None),
    ],
)
def test_text_empty(kind, a, b, change):
    result = compare_snapshots(
        Snapshot(200, {}, a, kind), Snapshot(200, {}, b, kind), ComparisonRules()
    )
    assert [d["change_type"] for d in result.differences] == (
        [change] if change else []
    )


def test_empty_body_vs_json_null():
    result = compare_snapshots(
        Snapshot(200, {}, None, "empty"),
        Snapshot(200, {}, None, "json"),
        ComparisonRules(),
    )
    d = result.differences[0]
    assert d["old_type"] == "empty_body" and d["new_type"] == "json_body"
    assert not d["old_present"] and d["new_present"]


@pytest.mark.parametrize(
    "kind,error,status,expected",
    [
        ("omitted", {"code": "unsupported_content_type"}, 200, "partial"),
        ("binary", None, 200, "partial"),
        ("omitted", {"code": "response_too_large"}, 200, "partial"),
        ("omitted", {"code": "timeout"}, None, "unavailable"),
        ("omitted", {"code": "timeout"}, 200, "unavailable"),
    ],
)
def test_incomplete_captures(kind, error, status, expected):
    result = compare_snapshots(
        Snapshot(200, {}, "original", "text"),
        Snapshot(status, {}, None, kind, error),
        ComparisonRules(),
    )
    assert (
        result.comparison_status == expected and not result.differences and result.notes
    )


def test_redacted_values_are_unknown_and_sensitive_values_never_leak():
    result = compare(
        {"password": "old-secret", "normal": "[REDACTED]", "value": 1},
        {"password": "new-secret", "normal": "something", "value": 2},
    )
    assert result.comparison_status == "partial"
    assert [d["path"] for d in result.differences] == ["/value"]
    assert "secret" not in str(result)


def test_large_values_use_previews_and_limits_are_explicit():
    result = compare("a" * 10000, "b" * 10000)
    assert result.differences[0]["old_value"] is None
    assert result.differences[0]["old_value_truncated"]
    assert compare("a" * 2_300_000, "b").comparison_status == "limited"
    result = compare(list(range(MAX_DIFFERENCES + 10)), [None] * (MAX_DIFFERENCES + 10))
    assert (
        result.comparison_status == "limited"
        and len(result.differences) == MAX_DIFFERENCES
    )
    deep = 0
    for _ in range(70):
        deep = {"x": deep}
    assert compare(deep, deep).comparison_status == "limited"
    assert compare([0] * 50001, []).comparison_status == "limited"


def test_order_and_result_determinism():
    a = {"z": 1, "b": [True, 2], "a": None}
    b = {"b": [False], "a": "", "c": 3}
    first = compare(a, b)
    for _ in range(3):
        assert compare(dict(reversed(list(a.items()))), b) == first


def test_unordered_large_integers_are_not_rounded():
    assert compare({"n": 10**35}, {"n": 1e35}).comparison_status == "identical"
    assert (
        compare(
            [10**35 + 1], [10**35 + 2], unordered_array_paths=[""]
        ).comparison_status
        == "different"
    )
    assert (
        compare([10**35], [1e35], unordered_array_paths=[""]).comparison_status
        == "identical"
    )
    assert compare({"x" * 5000: 1}, {"x" * 5000: 2}).comparison_status == "limited"

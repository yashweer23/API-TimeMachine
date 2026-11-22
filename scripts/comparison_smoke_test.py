"""Live record -> replay -> compare -> change rules -> historical retrieval.

Creates development projects, recordings, replay sessions, and comparisons.
"""

import argparse
import json
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8002")
    parser.add_argument("--v1", default="http://sample-api:8001")
    parser.add_argument("--v2", default="http://sample-api-v2:8001")
    args = parser.parse_args()

    def call(path, method="GET", body=None):
        request = Request(
            args.backend.rstrip("/") + "/api" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=150) as response:
            return json.load(response)

    project = call(
        "/projects", "POST", {"name": "Comparison smoke v1 to v2", "base_url": args.v1}
    )
    cases = [
        "unchanged",
        "added",
        "removed",
        "value",
        "type",
        "nested",
        "array",
        "status",
        "headers",
        "timestamp",
        "text",
        "empty",
        "unordered",
    ]
    originals = [
        call(
            f"/projects/{project['id']}/requests/send",
            "POST",
            {"endpoint_path": "/regression/" + case, "name": case},
        )
        for case in cases
    ]
    results = []
    comparisons = []
    for start in range(0, len(cases), 10):
        session = call(
            f"/projects/{project['id']}/replay-sessions",
            "POST",
            {
                "name": f"Regression cases {start + 1}",
                "target_base_url": args.v2,
                "recording_ids": [r["id"] for r in originals[start : start + 10]],
            },
        )
        assert session["status"] == "completed", session
        results.extend(call("/replay-results/" + r["id"]) for r in session["results"])
        overview = call("/replay-sessions/" + session["id"] + "/compare", "POST", {})
        assert overview["totals"]["compared"] == len(session["results"])
        comparisons.extend(call("/comparisons/" + c["id"]) for c in overview["items"])
    mapped = dict(zip(cases, comparisons))
    assert (
        mapped["unchanged"]["comparison_status"]
        == mapped["empty"]["comparison_status"]
        == "identical"
    )
    expected = {
        "added": ("/enabled", "field_added"),
        "removed": ("/legacy", "field_removed"),
        "value": ("/city", "value_changed"),
        "type": ("/age", "type_changed"),
        "nested": ("/profile/address/city", "value_changed"),
        "array": ("/roles/1", "value_changed"),
        "timestamp": ("/generated_at", "value_changed"),
        "text": ("", "text_changed"),
    }
    for case, (path, kind) in expected.items():
        body = [
            (d["path"], d["change_type"])
            for d in mapped[case]["differences"]
            if d["scope"] == "body"
        ]
        assert body == [(path, kind)], (case, body)
    assert mapped["status"]["counts"]["status_changed"] == 1
    assert mapped["headers"]["counts"]["header_changed"] == 2
    assert mapped["unordered"]["counts"]["value_changed"] == 2
    print(
        "PASS: 13 deterministic fixtures; JSON/status/multivalue headers/text/empty responses"
    )
    for old, result, comparison in zip(originals, results, comparisons):
        assert (
            call("/replay-results/" + result["id"] + "/compare", "POST", {})["id"]
            == comparison["id"]
        )
        assert call("/recordings/" + old["id"]) == old
        assert call("/replay-results/" + result["id"]) == result
    print("PASS: comparisons are idempotent; original and replay snapshots unchanged")
    rules = call(f"/projects/{project['id']}/comparison-settings")["rules"]
    rules["ignored_json_paths"] = ["/generated_at"]
    rules["unordered_array_paths"] = ["/roles"]
    call(f"/projects/{project['id']}/comparison-settings", "PUT", rules)
    for case in ["timestamp", "unordered"]:
        old = mapped[case]
        new = call(
            "/replay-results/" + old["replay_result_id"] + "/compare", "POST", {}
        )
        assert new["comparison_status"] == "identical" and new["id"] != old["id"], new
        historical = call("/comparisons/" + old["id"])
        assert (
            historical["differences"] == old["differences"]
            and not historical["is_current"]
        )
        assert (
            call("/replay-results/" + old["replay_result_id"] + "/comparison")["id"]
            == new["id"]
        )
    history = call(f"/projects/{project['id']}/comparisons")
    assert history["total"] == 15
    print(
        "PASS: ignored timestamp and unordered array rules; retained history and current selection"
    )
    print("Comparison project:", project["id"])
    print("Historical comparison:", mapped["timestamp"]["id"])


if __name__ == "__main__":
    main()

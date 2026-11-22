"""Live Phase 4: record ten cases, replay, compare, analyze, set policies and export.

Creates a development project and immutable evidence; never deletes previous data.
The transport fixture waits 25 seconds on v2 and requires capture timeout <25s.
"""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8002")
    parser.add_argument("--v1", default="http://sample-api:8001")
    parser.add_argument("--v2", default="http://sample-api-v2:8001")
    args = parser.parse_args()

    def call(path, method="GET", body=None, raw=False):
        req = Request(
            args.backend.rstrip("/") + "/api" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=150) as r:
            text = r.read().decode()
            return text if raw else json.loads(text)

    project = call(
        "/projects",
        "POST",
        {"name": "Compatibility smoke v1 to v2", "base_url": args.v1},
    )
    cases = [
        "unchanged",
        "required-removed",
        "type",
        "added",
        "value",
        "status",
        "error",
        "header",
        "timestamp",
        "transport",
    ]
    originals = [
        call(
            f"/projects/{project['id']}/requests/send",
            "POST",
            {"endpoint_path": "/compatibility/" + case, "name": case},
        )
        for case in cases
    ]
    assert all(r["response_status"] == 200 for r in originals)
    session = call(
        f"/projects/{project['id']}/replay-sessions",
        "POST",
        {
            "name": "Ten compatibility cases",
            "recording_ids": [r["id"] for r in originals],
            "target_base_url": args.v2,
        },
    )
    results = [call("/replay-results/" + r["id"]) for r in session["results"]]
    assert results[-1]["outcome"] == "transport_error", results[-1]
    compared = call(f"/replay-sessions/{session['id']}/compare", "POST", {})
    snapshots = [call("/comparisons/" + c["id"]) for c in compared["items"]]
    first = call(f"/replay-sessions/{session['id']}/analyze", "POST", {})
    assert first["summary"]["confirmed_breaking"] == 0
    first_report = call("/compatibility-runs/" + first["id"] + "/report", raw=True)
    policies = json.loads(
        (
            Path(__file__).resolve().parents[1] / "examples/compatibility-policies.json"
        ).read_text()
    )
    call(f"/projects/{project['id']}/compatibility-policies", "PUT", policies)
    second = call(f"/replay-sessions/{session['id']}/analyze", "POST", {})
    assert (
        second["id"] != first["id"]
        and second["verdict"] == "incompatible_with_configured_contract"
    ), second
    summary = second["summary"]
    assert (
        summary["compared"] == 10
        and summary["identical"] == 1
        and summary["changed"] == 8
    ), summary
    assert (
        summary["confirmed_breaking"] == 4
        and summary["transport_failures"] == 1
        and summary["unassessed"] == 2
    ), summary
    assert (
        call(f"/replay-sessions/{session['id']}/analyze", "POST", {})["id"]
        == second["id"]
    )
    assert (
        call("/compatibility-runs/" + first["id"] + "/report", raw=True) == first_report
    )
    findings = call("/compatibility-runs/" + second["id"] + "/findings?limit=100")[
        "items"
    ]
    expected = {
        "required-removed": ("contract.required_path", "confirmed_breaking"),
        "type": ("contract.type", "confirmed_breaking"),
        "added": ("policy.additional_allowed", "informational"),
        "value": ("default.unassessed", "unassessed"),
        "status": ("policy.allowed_status", "informational"),
        "error": ("contract.status", "confirmed_breaking"),
        "header": ("contract.required_header", "confirmed_breaking"),
        "timestamp": ("policy.dynamic_value", "informational"),
        "transport": ("evidence.http_missing", "unassessed"),
    }
    for case, (rule, classification) in expected.items():
        assert any(
            f["endpoint_path"] == "/compatibility/" + case
            and f["rule_id"] == rule
            and f["classification"] == classification
            for f in findings
        ), (case, findings)
    assert not any(f["endpoint_path"] == "/compatibility/unchanged" for f in findings)
    for original, result, comparison in zip(originals, results, snapshots):
        assert call("/recordings/" + original["id"]) == original
        assert call("/replay-results/" + result["id"]) == result
        assert call("/comparisons/" + comparison["id"]) == comparison
    report = call("/compatibility-runs/" + second["id"] + "/report")
    html = call("/compatibility-runs/" + second["id"] + "/report?format=html", raw=True)
    assert report["summary"] == summary and report["omitted_findings"] == 0
    assert "<script" not in html and "Frozen policies" in html
    assert call(f"/projects/{project['id']}/compatibility-runs")["total"] == 2
    print(
        "PASS: ten live compatibility fixtures, transport timeout separate from HTTP 500, four explicit violations"
    )
    print(
        "PASS: policy precedence, deterministic idempotence, immutable source evidence and historical report exports"
    )
    print("Compatibility project:", project["id"])
    print("Compatibility run:", second["id"])


if __name__ == "__main__":
    main()

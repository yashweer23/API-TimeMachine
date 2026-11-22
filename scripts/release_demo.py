"""Prepare a genuine local demonstration using saved HTTP evidence.

Creates one project, one baseline, one replay and two historical assessments.
Never deletes data or executes mutating HTTP methods at the target.
"""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        default="http://127.0.0.1:5175",
        help="Frontend proxy or backend URL",
    )
    parser.add_argument("--v1", help="Override the configured sample v1 target")
    parser.add_argument("--v2", help="Override the configured sample v2 target")
    parser.add_argument(
        "--report-dir", help="Optional local directory for real JSON and HTML downloads"
    )
    args = parser.parse_args()

    def call(path, method="GET", body=None, raw=False):
        request = Request(
            args.backend.rstrip("/") + "/api" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=150) as response:
            payload = response.read()
            return payload if raw else json.loads(payload)

    config = call("/config")
    v1, v2 = (
        args.v1 or config["sample_v1_base_url"],
        args.v2 or config["sample_v2_base_url"],
    )
    if not v1 or not v2:
        parser.error(
            "Configure allowed SAMPLE_V1_BASE_URL/SAMPLE_V2_BASE_URL or supply --v1 and --v2."
        )
    project = call(
        "/projects",
        "POST",
        {
            "name": "Sample API Regression Testing",
            "base_url": v1,
            "description": "Deterministic release demonstration using real saved sample responses.",
        },
    )
    original = call(
        f"/projects/{project['id']}/requests/send",
        "POST",
        {
            "method": "GET",
            "endpoint_path": "/users/1",
            "name": "User v1 baseline",
            "environment_label": "sample-v1",
        },
    )
    assert original["response_status"] == 200 and not original["execution_error"], (
        original
    )
    original = call("/recordings/" + original["id"], "PATCH", {"is_baseline": True})
    session = call(
        "/recordings/" + original["id"] + "/replay",
        "POST",
        {"target_base_url": v2, "name": "Sample user v1 to v2"},
    )
    result = call("/replay-results/" + session["results"][0]["id"])
    assert (
        result["response_status"] == 200
        and result["response_body"] != original["response_body"]
    )
    initial = call("/replay-sessions/" + session["id"] + "/assess", "POST", {})
    assert initial["summary"]["confirmed_breaking"] == 0
    policy = {
        "endpoints": [
            {
                "method": "GET",
                "endpoint_path": "/users/1",
                "expected_status_codes": [200],
                "required_json_paths": ["/data/id", "/data/name"],
                "expected_types": {"/data/id": "integer"},
                "allowed_content_types": ["application/json"],
                "allow_additional_fields": True,
                "dynamic_json_paths": ["/version"],
            }
        ]
    }
    call("/projects/" + project["id"] + "/compatibility-policies", "PUT", policy)
    final = call("/replay-sessions/" + session["id"] + "/assess", "POST", {})
    assert (
        final["verdict"] == "incompatible_with_configured_contract"
        and final["summary"]["confirmed_breaking"] == 2
    ), final
    assert final["id"] != initial["id"]
    assert (
        call("/replay-sessions/" + session["id"] + "/assess", "POST", {})["id"]
        == final["id"]
    )
    assert call("/recordings/" + original["id"]) == original
    assert call("/replay-results/" + result["id"]) == result
    comparison = call("/comparisons/" + final["analyses"][0]["comparison_id"])
    assert all(
        comparison["counts"][kind] > 0
        for kind in ["type_changed", "field_added", "field_removed", "value_changed"]
    )
    reports = {
        format: call(
            "/compatibility-runs/" + final["id"] + "/report?format=" + format, raw=True
        )
        for format in ["json", "html"]
    }
    report = json.loads(reports["json"])
    assert report["summary"] == final["summary"] and report["omitted_findings"] == 0
    assert call("/projects/" + project["id"] + "/compatibility-runs")["total"] == 2
    assert (
        call("/projects/" + project["id"] + "/recordings?search=baseline&method=GET")[
            "total"
        ]
        == 1
    )
    if args.report_dir:
        directory = Path(args.report_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for format, payload in reports.items():
            (directory / ("api-timemachine-demo." + format)).write_bytes(payload)
    print(
        "PASS: actual create -> GET capture -> baseline -> replay -> compare/analyze -> policy -> historical reports"
    )
    print(
        "PASS: 2 explicit contract violations; original/replay evidence unchanged; repeated assessment reuses IDs"
    )
    print("Project:", project["id"])
    print("Replay:", args.backend.rstrip("/") + "/replay/sessions/" + session["id"])
    print(
        "Report:",
        args.backend.rstrip("/")
        + f"/reports?project={project['id']}&session={session['id']}&run={final['id']}",
    )


if __name__ == "__main__":
    main()

"""Live v1 -> v2 replay smoke test. Creates a project, recordings, and sessions."""

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
        "/projects", "POST", {"name": "Replay smoke · v1 to v2", "base_url": args.v1}
    )
    endpoint = f"/projects/{project['id']}/requests/send"
    originals = [
        call(endpoint, "POST", payload)
        for payload in [
            {"endpoint_path": "/users/1", "name": "User v1"},
            {"endpoint_path": "/products", "name": "Products v1"},
            {
                "endpoint_path": "/echo",
                "method": "POST",
                "body": {"message": "replay smoke"},
                "name": "Echo v1",
            },
        ]
    ]
    assert all(r["response_status"] == 200 for r in originals), originals
    session = call(
        f"/projects/{project['id']}/replay-sessions",
        "POST",
        {
            "name": "v2 regression smoke",
            "target_base_url": args.v2,
            "recording_ids": [r["id"] for r in originals],
            "confirm_side_effects": True,
        },
    )
    assert session["status"] == "completed" and session["completed_requests"] == 3, (
        session
    )
    assert session["http_responses"] == 3 and session["failed_requests"] == 0
    results = [call("/replay-results/" + r["id"]) for r in session["results"]]
    user = results[0]["response_body"]["data"]
    assert (
        user["full_name"] == "Maya Chen"
        and user["id"] == "1"
        and user["account_status"] == "active"
    )
    assert "name" not in user and "role" not in user and "active" not in user
    assert results[1]["response_body"]["data"][0]["price"] == "29.00"
    assert "in_stock" not in results[1]["response_body"]["data"][0]
    assert results[2]["response_status"] == 201
    assert results[2]["response_body"]["body"] == {"message": "replay smoke"}
    for original, result in zip(originals, results):
        assert call("/recordings/" + original["id"]) == original
        assert result["original_recording"] == original
    print(
        "PASS: batch v1 -> v2; renamed, added, removed, type, and HTTP-status changes captured"
    )
    print("PASS: original snapshots unchanged; replay results stored separately")
    single = call(
        "/recordings/" + originals[0]["id"] + "/replay",
        "POST",
        {"target_base_url": args.v2, "name": "Single replay"},
    )
    assert single["id"] != session["id"] and single["total_requests"] == 1
    history = call(f"/projects/{project['id']}/replay-sessions")
    assert history["total"] == 2
    assert call("/replay-sessions/" + session["id"])["completed_requests"] == 3
    assert len(call("/replay-sessions/" + session["id"] + "/results")) == 3
    print("PASS: single replay, repeatable sessions, and persisted history")
    secret_original = call(
        endpoint,
        "POST",
        {
            "method": "POST",
            "endpoint_path": "/echo",
            "headers": {"Authorization": "Bearer original-demo-token"},
            "body": {"password": "original-demo-password"},
        },
    )
    secret_session = call(
        "/recordings/" + secret_original["id"] + "/replay",
        "POST",
        {
            "name": "Transient credential smoke",
            "target_base_url": args.v2,
            "confirm_side_effects": True,
            "temporary_headers": {"Authorization": "Bearer transient-demo-token"},
            "override": {"body": {"password": "transient-demo-password"}},
        },
    )
    secret_result = call("/replay-results/" + secret_session["results"][0]["id"])
    assert secret_result["response_status"] == 201, secret_result
    for secret in [
        "original-demo-token",
        "original-demo-password",
        "transient-demo-token",
        "transient-demo-password",
    ]:
        assert secret not in json.dumps(secret_result)
    print("PASS: transient credentials and echoed body replacements are redacted")
    print("Replay session:", session["id"])
    print("Project:", project["id"])


if __name__ == "__main__":
    main()

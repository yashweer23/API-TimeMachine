"""Run against the running development stack; creates one sample project and captures."""

import argparse
import json
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8002")
    parser.add_argument("--target", default="http://sample-api:8001")
    args = parser.parse_args()

    def call(path, method="GET", body=None):
        request = Request(
            args.backend.rstrip("/") + "/api" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    assert call("/health")["status"] == "ok"
    project = call(
        "/projects", "POST", {"name": "Smoke test · sample v1", "base_url": args.target}
    )
    send_path = f"/projects/{project['id']}/requests/send"
    get = call(send_path, "POST", {"method": "GET", "endpoint_path": "/users"})
    assert get["response_status"] == 200 and get["execution_error"] is None, get
    assert get["response_body"]["data"][0]["name"] == "Maya Chen"
    print("PASS: real GET /users capture")
    payload = {
        "message": "live-smoke-test",
        "password": "secret-for-verification",
        "nested": {"enabled": False},
    }
    post = call(
        send_path,
        "POST",
        {
            "method": "POST",
            "endpoint_path": "/echo",
            "body": payload,
            "headers": {"Authorization": "Bearer test-only-credential"},
        },
    )
    assert post["response_status"] == 200 and post["execution_error"] is None, post
    assert post["response_body"]["body"]["message"] == "live-smoke-test"
    assert post["response_body"]["body"]["nested"]["enabled"] is False
    assert "secret-for-verification" not in json.dumps(post)
    assert "test-only-credential" not in json.dumps(post)
    print("PASS: real POST /echo, JSON types, outgoing and echoed secret redaction")
    updated = call(
        "/recordings/" + get["id"],
        "PATCH",
        {"name": "Users reference v1", "is_baseline": True, "environment_label": "v1"},
    )
    assert updated["is_baseline"] and updated["name"] == "Users reference v1"
    fresh = call("/recordings/" + get["id"])
    assert fresh["is_baseline"] and fresh["response_body"] == get["response_body"]
    page = call(f"/projects/{project['id']}/recordings?baseline=true")
    assert page["total"] == 1 and page["items"][0]["id"] == get["id"]
    print("PASS: rename, baseline, listing, and fresh-request persistence")
    failed_http = call(send_path, "POST", {"endpoint_path": "/users/999"})
    assert (
        failed_http["response_status"] == 404 and failed_http["execution_error"] is None
    )
    print("PASS: HTTP 404 captured without a false connection failure")
    print(f"Smoke test complete. Project: {project['id']}")


if __name__ == "__main__":
    main()

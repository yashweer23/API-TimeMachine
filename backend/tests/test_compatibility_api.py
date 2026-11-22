import json
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from app.models.replay import ReplayResult, ReplaySession
from app.models.entities import Recording
from conftest import mock_response


def prepare(
    client,
    project,
    transport,
    old=None,
    new=None,
    status=200,
    path="/users/1",
    headers=None,
):
    transport(
        lambda req: mock_response(
            body=old if old is not None else {"id": 1, "name": "Maya"}, headers=headers
        )
    )
    original = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": path}
    ).json()
    transport(
        lambda req: mock_response(
            body=new if new is not None else {"name": "Maya"},
            status=status,
            headers=headers,
        )
    )
    session = client.post(
        "/api/recordings/" + original["id"] + "/replay",
        json={"target_base_url": "https://api.example.test/v2"},
    ).json()
    result = client.get("/api/replay-results/" + session["results"][0]["id"]).json()
    comparison = client.post(
        "/api/replay-results/" + result["id"] + "/compare", json={}
    ).json()
    return original, session, result, comparison


def test_workflow_history_reports_and_source_immutability(client, project, transport):
    original, session, result, comparison = prepare(client, project, transport)
    route = f"/api/replay-sessions/{session['id']}"
    p = f"/api/projects/{project['id']}/compatibility-policies"
    assert client.get(p).json()["policies"] == {"endpoints": []}
    response = client.post(route + "/analyze", json={})
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["verdict"] == "potential_compatibility_issues"
    assert first["summary"]["compared"] == first["summary"]["changed"] == 1
    assert client.post(route + "/analyze", json={}).json()["id"] == first["id"]
    first_report = client.get(f"/api/compatibility-runs/{first['id']}/report").text
    saved = client.put(
        p,
        json={
            "endpoints": [
                {
                    "endpoint_path": "/users/1",
                    "required_json_paths": ["/id"],
                    "expected_status_codes": [200],
                }
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    assert not client.get(route + "/compatibility").json()["is_current"]
    second = client.post(route + "/analyze", json={}).json()
    assert (
        second["id"] != first["id"]
        and second["verdict"] == "incompatible_with_configured_contract"
    )
    assert second["summary"]["confirmed_breaking"] == 1
    findings = client.get(
        f"/api/compatibility-runs/{second['id']}/findings?classification=confirmed_breaking&severity=high&method=GET&endpoint=users&search=Required&limit=1"
    ).json()
    assert findings["total"] == 1
    f = findings["items"][0]
    assert f["difference_id"] and f["comparison_id"] == comparison["id"]
    assert f["evidence"]["old_value"] == 1 and f["evidence"]["new_present"] is False
    analysis = second["analyses"][0]
    assert (
        client.get(f"/api/compatibility-analyses/{analysis['id']}").json() == analysis
    )
    assert (
        client.post(f"/api/comparisons/{comparison['id']}/analyze", json={}).json()
        == analysis
    )
    assert (
        client.get(f"/api/comparisons/{comparison['id']}/compatibility").json()
        == analysis
    )
    assert (
        client.get(f"/api/compatibility-analyses/{analysis['id']}/findings").json()[
            "total"
        ]
        >= 1
    )
    history = client.get(
        f"/api/projects/{project['id']}/compatibility-runs?limit=1"
    ).json()
    assert history["total"] == 2 and len(history["items"]) == 1
    assert (
        client.get(f"/api/compatibility-runs/{first['id']}/report").text == first_report
    )
    report = client.get(f"/api/compatibility-runs/{second['id']}/report?format=html")
    assert report.status_code == 200 and "text/html" in report.headers["content-type"]
    assert (
        "attachment;" in report.headers["content-disposition"]
        and "nosniff" == report.headers["x-content-type-options"]
    )
    assert "Required JSON path" in report.text and "Unexecuted endpoints" in report.text
    assert client.get("/api/recordings/" + original["id"]).json() == original
    assert client.get("/api/replay-results/" + result["id"]).json() == result
    assert client.get("/api/comparisons/" + comparison["id"]).json() == comparison
    # Reverting policy reuses the exact original run; creates no extra rows.
    client.put(p, json={"endpoints": []})
    assert client.post(route + "/analyze", json={}).json()["id"] == first["id"]
    assert client.get(route + "/compatibility").json()["id"] == first["id"]
    assert (
        client.get(f"/api/projects/{project['id']}/compatibility-runs").json()["total"]
        == 2
    )


def test_missing_comparison_and_transport_failure(client, project, transport, engine):
    transport(lambda req: mock_response(body={"id": 1}))
    original = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": "/users"}
    ).json()
    import httpx

    def fail(req):
        raise httpx.ConnectError("Do not expose internal credentials", request=req)

    transport(fail)
    session = client.post(
        "/api/recordings/" + original["id"] + "/replay",
        json={"target_base_url": "https://api.example.test/v2"},
    ).json()
    route = f"/api/replay-sessions/{session['id']}"
    before = client.post(route + "/analyze", json={}).json()
    assert (
        before["summary"]["missing_comparisons"] == 1
        and before["verdict"] == "insufficient_evidence"
    )
    client.post(route + "/compare", json={})
    after = client.post(route + "/analyze", json={}).json()
    assert after["id"] != before["id"] and after["summary"]["transport_failures"] == 1
    assert (
        after["summary"]["unassessed"] == 1
        and after["verdict"] == "insufficient_evidence"
    )
    assert not after["summary"]["confirmed_breaking"]
    with Session(engine) as db:
        db.get(ReplaySession, UUID(session["id"])).status = "running"
        db.commit()
    assert client.post(route + "/analyze", json={}).status_code == 409
    assert (
        client.post(
            f"/api/comparisons/{after['analyses'][0]['comparison_id']}/analyze", json={}
        ).status_code
        == 409
    )


def test_policy_exact_endpoint_match_ignores_and_filters(client, project, transport):
    _, session, _, comparison = prepare(client, project, transport)
    path = f"/api/projects/{project['id']}"
    client.put(
        path + "/compatibility-policies",
        json={
            "endpoints": [
                {
                    "method": "POST",
                    "endpoint_path": "/users/1",
                    "required_json_paths": ["/id"],
                },
                {"endpoint_path": "/users", "required_json_paths": ["/id"]},
            ]
        },
    )
    run = client.post(f"/api/replay-sessions/{session['id']}/analyze", json={}).json()
    assert (
        run["analyses"][0]["effective_policy"] is None
        and run["summary"]["confirmed_breaking"] == 0
    )
    client.put(path + "/comparison-settings", json={"ignored_json_paths": ["/id"]})
    comp = client.post(
        "/api/replay-results/" + comparison["replay_result_id"] + "/compare", json={}
    ).json()
    assert comp["counts"]["field_removed"] == 0
    client.put(
        path + "/compatibility-policies",
        json={
            "endpoints": [{"endpoint_path": "/users/1", "required_json_paths": ["/id"]}]
        },
    )
    run = client.post(f"/api/replay-sessions/{session['id']}/analyze", json={}).json()
    f = client.get(
        f"/api/compatibility-runs/{run['id']}/findings?classification=confirmed_breaking"
    ).json()["items"][0]
    assert f["difference_id"] is None and f["rule_id"] == "contract.required_path"
    assert (
        client.get(
            f"/api/compatibility-runs/{run['id']}/findings?severity=unrated"
        ).json()["total"]
        >= 1
    )
    assert (
        client.get(f"/api/compatibility-runs/{run['id']}/findings?method=PATCH").json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get(
            f"/api/compatibility-runs/{run['id']}/findings?classification=bad"
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/compatibility-runs/{run['id']}/findings?limit=101"
        ).status_code
        == 422
    )


def test_reports_escape_redact_bound_and_stay_historical(
    client, project, transport, monkeypatch
):
    _, session, _, _ = prepare(
        client,
        project,
        transport,
        old={"value": "before"},
        new={"value": "<script>alert(1)</script>", "password": "report-secret-123"},
    )
    run = client.post(f"/api/replay-sessions/{session['id']}/analyze", json={}).json()
    url = f"/api/compatibility-runs/{run['id']}/report"
    js = client.get(url).json()
    assert "report-secret-123" not in json.dumps(js)
    html = client.get(url + "?format=html").text
    assert (
        "<script>" not in html
        and "&lt;script&gt;" in html
        and "report-secret-123" not in html
    )
    assert "is_current" not in js and js["included_findings"] > 0
    from app.services import compatibility_reports as reports

    monkeypatch.setattr(reports, "MAX_REPORT_FINDINGS", 1)
    limited = client.get(url).json()
    assert (
        limited["included_findings"] == 1
        and limited["omitted_findings"] == len(js["findings"]) - 1
    )
    monkeypatch.setattr(reports, "MAX_REPORT_BYTES", 20)
    assert client.get(url).status_code == 413
    assert client.get(url + "?format=pdf").status_code == 422


def test_ids_validation_and_project_integrity(client, project, transport, engine):
    _, session, result, comp = prepare(client, project, transport)
    assert client.get(f"/api/comparisons/{comp['id']}/compatibility").status_code == 404
    assert (
        client.get(f"/api/replay-sessions/{session['id']}/compatibility").status_code
        == 404
    )
    for route in ("compatibility-runs", "compatibility-analyses"):
        assert client.get(f"/api/{route}/{uuid4()}").status_code == 404
    assert client.post("/api/comparisons/not-uuid/analyze", json={}).status_code == 422
    assert (
        client.put(
            f"/api/projects/{project['id']}/compatibility-policies",
            json={
                "endpoints": [
                    {"endpoint_path": "/users", "required_json_paths": ["$.x"]}
                ]
            },
        ).status_code
        == 422
    )
    other = client.post(
        "/api/projects", json={"name": "Other", "base_url": "https://api.example.test"}
    ).json()
    with Session(engine) as db:
        r = db.get(ReplayResult, UUID(result["id"]))
        db.get(Recording, r.original_recording_id).project_id = UUID(other["id"])
        db.commit()
    assert (
        client.post("/api/comparisons/" + comp["id"] + "/analyze", json={}).status_code
        == 409
    )
    assert (
        client.post(
            "/api/replay-sessions/" + session["id"] + "/analyze", json={}
        ).status_code
        == 409
    )

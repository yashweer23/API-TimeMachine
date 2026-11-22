"""Final integration, bounded execution and query projections."""

from uuid import UUID
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from app.models.entities import Recording
from app.services import catalog
from conftest import mock_response
from test_comparisons import make_replay
from test_compatibility_api import prepare


def test_history_queries_do_not_scale_per_run(client, project, transport, engine):
    _, session, _, _ = prepare(client, project, transport)

    def add(index):
        assert (
            client.put(
                f"/api/projects/{project['id']}/compatibility-policies",
                json={
                    "endpoints": [
                        {
                            "endpoint_path": "/users/1",
                            "required_json_paths": ["/required" + str(index)],
                        }
                    ]
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/replay-sessions/{session['id']}/analyze", json={}
            ).status_code
            == 200
        )

    def selects():
        queries = []

        def count(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                queries.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            response = client.get(f"/api/projects/{project['id']}/compatibility-runs")
            assert response.status_code == 200, response.text
            return len(queries), response.json()["total"]
        finally:
            event.remove(engine, "before_cursor_execute", count)

    for i in range(2):
        add(i)
    small, total = selects()
    assert total == 2
    for i in range(2, 10):
        add(i)
    large, total = selects()
    assert total == 10
    print(f"HISTORY SQL SELECTS: 2 runs={small}; 10 runs={large}")
    assert large <= small + 1


def test_recording_summary_projection_and_literal_search(
    client, project, transport, engine
):
    transport(lambda req: mock_response(body={"data": "x" * 500}))
    ids = []
    for name, path in [("Find_100%", "/one"), ("Other", "/two")]:
        r = client.post(
            f"/api/projects/{project['id']}/requests/send",
            json={"name": name, "endpoint_path": path},
        ).json()
        ids.append(r["id"])
    response = client.get(
        f"/api/projects/{project['id']}/recordings?search=100%25&method=GET&limit=1"
    ).json()
    assert response["total"] == 1 and response["items"][0]["id"] == ids[0]
    assert "response_body" not in response["items"][0]
    assert (
        client.get(f"/api/projects/{project['id']}/recordings?method=DELETE").json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get(f"/api/projects/{project['id']}/recordings?method=BAD").status_code
        == 422
    )
    with Session(engine) as db:
        row = catalog.list_recordings(db, UUID(project["id"]), 20, 0, None)["items"][0]
        assert {
            "response_body",
            "request_body",
            "response_headers",
            "request_headers",
        } <= inspect(row).unloaded
        assert db.get(Recording, UUID(ids[0])).response_body == {"data": "x" * 500}


def test_assess_compares_then_analyzes_without_reexecution(client, project, transport):
    original, session, result = make_replay(client, project, transport)
    assert (
        client.get("/api/replay-results/" + result["id"] + "/comparison").status_code
        == 404
    )

    def no_outbound(req):
        raise AssertionError("Saved-evidence assessment must not execute HTTP")

    transport(no_outbound)
    route = "/api/replay-sessions/" + session["id"] + "/assess"
    response = client.post(route, json={})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["summary"]["compared"] == 1 and not run["summary"]["missing_comparisons"]
    assert client.post(route, json={}).json()["id"] == run["id"]
    assert client.get("/api/recordings/" + original["id"]).json() == original
    assert client.get("/api/replay-results/" + result["id"]).json() == result
    assert client.post(route, json={"extra": True}).status_code == 422


def test_shared_execution_rate_limit_blocks_capture_and_replay_without_http(
    client, project, transport, app
):
    calls = []
    transport(lambda req: (calls.append(req), mock_response(body={"ok": True}))[1])
    from app.core.execution_limits import ExecutionRateLimiter

    clock = [0.0]
    app.state.recorder.rate_limiter = ExecutionRateLimiter(2, clock=lambda: clock[0])
    first = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": "/one"}
    ).json()
    second = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": "/two"}
    ).json()
    assert (
        first["response_status"] == second["response_status"] == 200 and len(calls) == 2
    )
    limited = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": "/three"}
    ).json()
    assert (
        limited["response_status"] is None
        and limited["execution_error"]["code"] == "execution_rate_limited"
    )
    session = client.post(
        "/api/recordings/" + first["id"] + "/replay",
        json={"target_base_url": "https://api.example.test/v2"},
    ).json()
    assert session["results"][0]["outcome"] == "blocked" and len(calls) == 2
    clock[0] = 61.0
    allowed = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": "/four"}
    ).json()
    assert allowed["response_status"] == 200 and len(calls) == 3


def test_runtime_config_exposes_only_valid_allowlisted_sample_targets(client, settings):
    data = client.get("/api/config").json()
    assert data["sample_v1_base_url"] is None and data["sample_v2_base_url"] is None
    assert "database_url" not in data and "redact_fields" not in data
    settings.sample_v1_base_url = "https://api.example.test/v1"
    assert (
        client.get("/api/config").json()["sample_v1_base_url"]
        == "https://api.example.test/v1"
    )
    assert client.get("/api/health").json()["phase"] == 5


def test_report_and_history_validate_source_projects_without_loading_bodies(
    client, project, transport, engine
):
    original, session, _, _ = prepare(client, project, transport)
    run = client.post(f"/api/replay-sessions/{session['id']}/assess", json={}).json()
    other = client.post(
        "/api/projects", json={"name": "Other", "base_url": "https://api.example.test"}
    ).json()
    with Session(engine) as db:
        db.get(Recording, UUID(original["id"])).project_id = UUID(other["id"])
        db.commit()
    assert (
        client.get("/api/compatibility-runs/" + run["id"] + "/report").status_code
        == 409
    )
    assert (
        client.get(f"/api/projects/{project['id']}/compatibility-runs").status_code
        == 409
    )

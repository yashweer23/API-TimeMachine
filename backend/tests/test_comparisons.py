import json
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.comparison import Comparison, Difference
from app.models.entities import Recording
from app.models.replay import ReplayResult
from conftest import mock_response


def make_replay(
    client, project, transport, old=None, new=None, old_headers=None, new_headers=None
):
    transport(
        lambda req: mock_response(
            body=old or {"n": 1, "gone": None}, headers=old_headers
        )
    )
    original = client.post(
        f"/api/projects/{project['id']}/requests/send",
        json={"endpoint_path": "/users/1"},
    ).json()
    transport(
        lambda req: mock_response(
            status=201, body=new or {"n": "1", "added": True}, headers=new_headers
        )
    )
    response = client.post(
        "/api/recordings/" + original["id"] + "/replay",
        json={"target_base_url": "https://api.example.test/v2"},
    )
    assert response.status_code == 201, response.text
    session = response.json()
    result = client.get("/api/replay-results/" + session["results"][0]["id"]).json()
    return original, session, result


def test_compare_persist_idempotence_rules_history_and_sources(
    client, project, transport, engine
):
    original, session, result = make_replay(client, project, transport)
    path = "/api/replay-results/" + result["id"] + "/compare"
    response = client.post(path, json={})
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["comparison_status"] == "different"
    assert first["counts"]["type_changed"] == 1
    assert (
        first["counts"]["field_added"]
        == first["counts"]["field_removed"]
        == first["counts"]["status_changed"]
        == 1
    )
    assert client.post(path, json={}).json()["id"] == first["id"]
    assert (
        client.get("/api/replay-results/" + result["id"] + "/comparison").json()
        == first
    )
    assert client.get("/api/comparisons/" + first["id"]).json() == first
    body_diff = next(d for d in first["differences"] if d["path"] == "/gone")
    assert (
        body_diff["old_present"]
        and not body_diff["new_present"]
        and body_diff["old_value"] is None
    )
    settings = client.get(f"/api/projects/{project['id']}/comparison-settings").json()
    assert "date" in settings["rules"]["ignored_headers"]
    settings["rules"]["ignored_json_paths"] = ["/n", "/gone", "/added"]
    assert (
        client.put(
            f"/api/projects/{project['id']}/comparison-settings", json=settings["rules"]
        ).status_code
        == 200
    )
    assert not client.get("/api/comparisons/" + first["id"]).json()["is_current"]
    second = client.post(path, json={}).json()
    assert second["id"] != first["id"] and second["counts"]["type_changed"] == 0
    assert second["is_current"]
    assert (
        client.get("/api/replay-results/" + result["id"] + "/comparison").json()["id"]
        == second["id"]
    )
    old_again = client.post(path, json={"rules": first["effective_rules"]}).json()
    assert old_again["id"] == first["id"] and not old_again["is_current"]
    assert (
        client.get(f"/api/projects/{project['id']}/comparisons?limit=1").json()["total"]
        == 2
    )
    overview = client.post(
        "/api/replay-sessions/" + session["id"] + "/compare", json={}
    ).json()
    assert (
        overview["totals"]["compared"] == 1
        and overview["totals"]["differences"] == second["total_differences"]
    )
    assert (
        client.get("/api/replay-sessions/" + session["id"] + "/comparisons").json()
        == overview
    )
    assert client.get("/api/recordings/" + original["id"]).json() == original
    assert client.get("/api/replay-results/" + result["id"]).json() == result
    with Session(engine) as db:
        assert len(db.scalars(select(Comparison)).all()) == 2
        assert (
            len(db.scalars(select(Difference)).all())
            == first["total_differences"] + second["total_differences"]
        )


def test_rules_validation_missing_ids_and_project_relationship(
    client, project, transport, engine
):
    _, session, result = make_replay(client, project, transport)
    path = "/api/replay-results/" + result["id"] + "/compare"
    for invalid in [
        {"ignored_json_paths": ["$.x"]},
        {"ignored_headers": ["not a header"]},
        {"unordered_array_paths": ["/a"], "ignored_json_paths": ["/a/0"]},
        {"unknown": True},
    ]:
        assert client.post(path, json={"rules": invalid}).status_code == 422
        assert (
            client.put(
                f"/api/projects/{project['id']}/comparison-settings", json=invalid
            ).status_code
            == 422
        )
    assert (
        client.post("/api/replay-results/not-uuid/compare", json={}).status_code == 422
    )
    assert (
        client.post(f"/api/replay-results/{uuid4()}/compare", json={}).status_code
        == 404
    )
    assert (
        client.get("/api/replay-results/" + result["id"] + "/comparison").status_code
        == 404
    )
    other = client.post(
        "/api/projects", json={"name": "Other", "base_url": "https://api.example.test"}
    ).json()
    assert client.get(f"/api/projects/{other['id']}/comparisons").json()["total"] == 0
    with Session(engine) as db:
        r = db.get(ReplayResult, UUID(result["id"]))
        source = db.get(Recording, r.original_recording_id)
        source.project_id = UUID(other["id"])
        db.commit()
    assert client.post(path, json={}).status_code == 409
    assert (
        client.post(
            "/api/replay-sessions/" + session["id"] + "/compare", json={}
        ).status_code
        == 409
    )


def test_pending_is_not_cached_and_failures_are_incomparable(
    client, project, transport, engine
):
    _, _, result = make_replay(client, project, transport)
    with Session(engine) as db:
        row = db.get(ReplayResult, UUID(result["id"]))
        row.outcome = "running"
        db.commit()
    assert (
        client.post(
            "/api/replay-results/" + result["id"] + "/compare", json={}
        ).status_code
        == 409
    )
    with Session(engine) as db:
        row = db.get(ReplayResult, UUID(result["id"]))
        row.outcome = "transport_error"
        row.response_status = None
        row.response_body = None
        row.response_body_kind = "omitted"
        row.execution_error = {"code": "timeout", "message": "Timed out."}
        db.commit()
    response = client.post(
        "/api/replay-results/" + result["id"] + "/compare", json={}
    ).json()
    assert (
        response["comparison_status"] == "unavailable"
        and response["total_differences"] == 0
    )


def test_duplicate_headers_preserved_and_secrets_not_disclosed(
    client, project, transport
):
    headers = [
        ("Content-Type", "application/json"),
        ("X-Repeat", "one"),
        ("X-Repeat", "two"),
        ("Set-Cookie", "session=private-value"),
    ]
    original, _, result = make_replay(
        client, project, transport, old_headers=headers, new_headers=headers
    )
    assert original["response_headers"]["x-repeat"] == ["one", "two"]
    response = client.post(
        "/api/replay-results/" + result["id"] + "/compare", json={}
    ).json()
    assert "private-value" not in json.dumps(response)
    assert response["comparison_status"] == "partial"
    for difference in response["differences"]:
        values = client.get(
            f"/api/comparisons/{response['id']}/differences/{difference['id']}/values"
        )
        assert values.status_code == 200, values.text
        assert "private-value" not in values.text


def test_large_values_fetched_by_reference(client, project, transport, settings, app):
    # Increase the test capture cap; production default is 1 MiB.
    app.state.recorder.settings.max_response_bytes = 20000
    transport(lambda req: mock_response(body={"data": "a" * 5000}))
    original = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": "/users"}
    ).json()
    transport(lambda req: mock_response(body={"data": "b" * 5000}))
    app.state.recorder.settings.max_response_bytes = 20000
    session = client.post(
        "/api/recordings/" + original["id"] + "/replay",
        json={"target_base_url": "https://api.example.test/v2"},
    ).json()
    result_id = session["results"][0]["id"]
    comparison = client.post(
        "/api/replay-results/" + result_id + "/compare", json={}
    ).json()
    d = next(d for d in comparison["differences"] if d["scope"] == "body")
    assert d["old_value_truncated"] and d["old_value"] is None
    values = client.get(
        f"/api/comparisons/{comparison['id']}/differences/{d['id']}/values"
    ).json()
    assert values["old_value"] == "a" * 5000 and values["new_value"] == "b" * 5000
    assert (
        client.get(
            f"/api/comparisons/{comparison['id']}/differences/{uuid4()}/values"
        ).status_code
        == 404
    )

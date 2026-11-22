import asyncio
import json
from uuid import UUID, uuid4
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Recording
from app.models.replay import ReplayResult, ReplaySession
from app.services.replay_service import recover_interrupted_sessions
from conftest import mock_response


def capture(client, project, transport, **payload):
    transport(lambda request: mock_response(body={"name": "Maya", "id": 1}))
    r = client.post(
        f"/api/projects/{project['id']}/requests/send",
        json={"endpoint_path": "/users/1", **payload},
    )
    assert r.status_code == 201, r.text
    return r.json()


def replay(client, project, records, **changes):
    return client.post(
        f"/api/projects/{project['id']}/replay-sessions",
        json={
            "name": "v2 regression",
            "target_base_url": "https://api.example.test/v2",
            "recording_ids": [r["id"] for r in records],
            **changes,
        },
    )


def test_replay_get_changed_body_target_original_immutable(
    client, project, transport, engine
):
    original = capture(client, project, transport)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path == "/v2/users/1"
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "api.example.test"
        assert request.extensions["sni_hostname"] == "api.example.test"
        assert request.content == b""
        return mock_response(
            body={"id": "1", "full_name": "Maya", "account_status": "active"}
        )

    transport(handler)
    r = replay(client, project, [original])
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "completed"
    assert (
        s["total_requests"],
        s["completed_requests"],
        s["http_responses"],
        s["failed_requests"],
    ) == (1, 1, 1, 0)
    result = client.get("/api/replay-results/" + s["results"][0]["id"]).json()
    assert result["response_body"]["full_name"] == "Maya"
    assert result["original_recording"] == original
    assert client.get("/api/recordings/" + original["id"]).json() == original
    assert result["request_metadata"]["body_present"] is False
    with Session(engine) as db:
        assert len(db.scalars(select(Recording)).all()) == 1
        assert len(db.scalars(select(ReplaySession)).all()) == 1
        assert len(db.scalars(select(ReplayResult)).all()) == 1
    assert len(calls) == 1
    assert (
        client.get(f"/api/projects/{project['id']}/replay-sessions?limit=1").json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get("/api/replay-sessions/" + s["id"]).json()["results"][0]["id"]
        == result["id"]
    )
    assert (
        client.get("/api/replay-sessions/" + s["id"] + "/results").json()[0]["outcome"]
        == "http_response"
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutations_require_confirmation_and_execute_once(
    client, project, transport, method
):
    original = capture(
        client,
        project,
        transport,
        method=method,
        endpoint_path="/echo",
        body={"name": "original"},
    )
    count = []

    def handler(request):
        count.append(request.method)
        assert json.loads(request.content) == {"name": "original"}
        return mock_response(201, {"changed": True})

    transport(handler)
    assert replay(client, project, [original]).status_code == 409
    r = replay(client, project, [original], confirm_side_effects=True).json()
    assert count == [method]
    assert r["results"][0]["response_status"] == 201 and r["failed_requests"] == 0


def test_single_endpoint_uses_sessions_and_multiple_replays(client, project, transport):
    original = capture(client, project, transport)
    transport(lambda r: mock_response())
    ids = []
    for _ in range(2):
        r = client.post(
            "/api/recordings/" + original["id"] + "/replay",
            json={"target_base_url": "https://api.example.test/v2"},
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    assert ids[0] != ids[1]
    assert (
        client.get(f"/api/projects/{project['id']}/replay-sessions").json()["total"]
        == 2
    )


def test_batch_runs_in_selection_order_sequentially(client, project, transport):
    records = [
        capture(client, project, transport, endpoint_path="/users/" + str(i))
        for i in range(3)
    ]
    order = []
    active = 0

    async def handler(request):
        nonlocal active
        active += 1
        assert active == 1
        order.append(request.url.path)
        await asyncio.sleep(0.001)
        active -= 1
        return mock_response()

    transport(handler)
    s = replay(client, project, [records[2], records[0], records[1]]).json()
    assert s["completed_requests"] == 3
    assert order == ["/v2/users/2", "/v2/users/0", "/v2/users/1"]
    assert [r["ordinal"] for r in s["results"]] == [0, 1, 2]


@pytest.mark.parametrize("status", [400, 404, 500])
def test_http_errors_are_captured_responses(client, project, transport, status):
    original = capture(client, project, transport)
    transport(lambda r: mock_response(status, {"detail": "changed"}))
    session = replay(client, project, [original]).json()
    assert session["status"] == "completed" and session["failed_requests"] == 0
    assert session["http_responses"] == 1
    assert session["results"][0]["response_status"] == status
    assert session["results"][0]["execution_error"] is None


@pytest.mark.parametrize(
    "exc,code",
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection_error")],
)
def test_transport_failures_persist_and_post_is_not_retried(
    client, project, transport, exc, code
):
    original = capture(
        client, project, transport, method="POST", endpoint_path="/echo", body={}
    )
    calls = []

    def handler(request):
        calls.append(1)
        raise exc("secret=never-persist", request=request)

    transport(handler)
    s = replay(client, project, [original], confirm_side_effects=True).json()
    assert len(calls) == 1 and s["failed_requests"] == 1 and s["http_responses"] == 0
    assert s["status"] == "completed_with_errors"
    result = client.get("/api/replay-results/" + s["results"][0]["id"]).json()
    assert (
        result["response_status"] is None and result["execution_error"]["code"] == code
    )
    assert "never-persist" not in json.dumps(result)


def test_masked_values_never_replayed_and_temporary_credentials_not_persisted(
    client, project, transport, engine
):
    original = capture(
        client,
        project,
        transport,
        method="POST",
        endpoint_path="/echo",
        headers={
            "Authorization": "Bearer original-auth",
            "Cookie": "session=original-cookie",
        },
        query_parameters={"api_key": "original-query"},
        body={"password": "original-password"},
    )
    assert (
        replay(client, project, [original], confirm_side_effects=True).status_code
        == 422
    )
    actual = []

    def handler(request):
        actual.append(request)
        assert request.headers["authorization"] == "Bearer fresh-auth"
        assert "cookie" not in request.headers
        assert request.url.params["api_key"] == "fresh-query"
        assert json.loads(request.content)["unusualCredentialField"] == "fresh-body"
        return mock_response(
            body={
                "unlabeled": "prefix:fresh-auth",
                "fresh-body": "fresh-query",
                "short": "prefix:xy",
                "num": 123456,
            }
        )

    transport(handler)
    r = replay(
        client,
        project,
        [original],
        confirm_side_effects=True,
        temporary_headers={"Authorization": "Bearer fresh-auth", "X-Unusual": "xy"},
        overrides={
            original["id"]: {
                "headers": {"Cookie": None},
                "query_parameters": {"api_key": "fresh-query"},
                "body": {"unusualCredentialField": "fresh-body", "numeric": 123456},
            }
        },
    )
    assert r.status_code == 201, r.text
    result = client.get("/api/replay-results/" + r.json()["results"][0]["id"]).json()
    text = json.dumps(result)
    for secret in ["fresh-auth", "fresh-body", "fresh-query", "xy", "123456"]:
        assert secret not in text
    with Session(engine) as db:
        saved = db.scalar(select(ReplayResult))
        assert "fresh-auth" not in json.dumps(saved.request_metadata)
        assert "fresh-body" not in json.dumps(saved.response_body)
    assert len(actual) == 1


@pytest.mark.parametrize(
    "kind", ["missing", "malformed", "duplicate", "cross_project", "override_other"]
)
def test_invalid_selection_rejected_before_execution(client, project, transport, kind):
    original = capture(client, project, transport)
    ids = [original["id"]]
    changes = {}
    if kind == "missing":
        ids = [str(uuid4())]
    if kind == "malformed":
        ids = ["bad-id"]
    if kind == "duplicate":
        ids = ids * 2
    if kind == "cross_project":
        other = client.post(
            "/api/projects",
            json={"name": "Other", "base_url": "https://api.example.test"},
        ).json()
        ids = [capture(client, other, transport)["id"]]
    if kind == "override_other":
        changes = {"overrides": {str(uuid4()): {"body": {}}}}
    calls = []
    transport(lambda r: calls.append(r) or mock_response())
    r = replay(client, project, [], recording_ids=ids, **changes)
    assert r.status_code in {403, 404, 422}, r.text
    assert not calls


def test_unapproved_targets_schemes_headers_and_methods_rejected(
    client, project, transport
):
    original = capture(client, project, transport)
    assert (
        replay(
            client, project, [original], target_base_url="https://not-approved.test"
        ).status_code
        == 403
    )
    assert (
        replay(
            client, project, [original], target_base_url="file:///etc/passwd"
        ).status_code
        == 422
    )
    for key in ["Host", "Transfer-Encoding", "Proxy-Authorization"]:
        assert (
            replay(
                client, project, [original], temporary_headers={key: "secret"}
            ).status_code
            == 422
        )
    assert (
        replay(
            client,
            project,
            [original],
            overrides={original["id"]: {"method": "DELETE"}},
        ).status_code
        == 422
    )


def test_dns_rebinding_block_stored_distinct_from_transport(
    client, project, transport, app, monkeypatch
):
    original = capture(client, project, transport)

    async def resolve(*args):
        return ["8.8.8.8", "127.0.0.1"]

    monkeypatch.setattr(app.state.policy, "resolve", resolve)
    calls = []
    transport(lambda r: calls.append(r) or mock_response())
    s = replay(client, project, [original]).json()
    assert not calls and s["results"][0]["outcome"] == "blocked"
    assert s["failed_requests"] == 0 and s["error_requests"] == 1


def test_capture_errors_and_redirects_are_not_transport_failures(
    client, project, transport
):
    original = capture(client, project, transport)
    transport(lambda r: mock_response(raw=b'"' + b"x" * 2048 + b'"'))
    s = replay(client, project, [original]).json()
    assert s["results"][0]["outcome"] == "capture_error"
    assert (
        s["http_responses"] == 1
        and s["failed_requests"] == 0
        and s["error_requests"] == 1
    )
    calls = []
    transport(
        lambda r: (
            calls.append(r)
            or mock_response(
                302, headers={"location": "http://169.254.169.254"}, raw=b""
            )
        )
    )
    s = replay(client, project, [original]).json()
    assert len(calls) == 1 and s["results"][0]["response_status"] == 302


def test_session_deadline_skips_remaining_without_sending(
    client, project, transport, app
):
    records = [capture(client, project, transport) for _ in range(2)]
    app.state.replays.settings.replay_session_timeout_seconds = 0.02
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.2)
        return mock_response()

    transport(handler)
    s = replay(client, project, records).json()
    assert s["status"] == "timed_out" and len(calls) == 1
    assert (
        s["completed_requests"] == 2
        and s["skipped_requests"] == 1
        and s["failed_requests"] == 1
    )
    assert s["results"][1]["executed_at"] is None


def test_batch_limit_and_busy_rejection(client, project, transport, app):
    originals = [capture(client, project, transport) for _ in range(2)]
    app.state.replays.settings.replay_max_batch_size = 1
    assert replay(client, project, originals).status_code == 422
    app.state.replays.slots = asyncio.Semaphore(0)
    assert replay(client, project, originals[:1]).status_code == 429


@pytest.mark.parametrize("body_present", [False, True])
def test_no_body_vs_explicit_json_null(client, project, transport, body_present):
    original = capture(
        client, project, transport, **({"body": None} if body_present else {})
    )

    def handler(request):
        assert request.content == (b"null" if body_present else b"")
        return mock_response()

    transport(handler)
    assert replay(client, project, [original]).json()["status"] == "completed"


def test_legacy_null_body_requires_explicit_choice(client, project, transport, engine):
    original = capture(client, project, transport)
    with Session(engine) as db:
        db.get(Recording, UUID(original["id"])).request_body_present = None
        db.commit()
    assert replay(client, project, [original]).status_code == 422
    transport(lambda r: mock_response())
    assert (
        replay(
            client, project, [original], overrides={original["id"]: {"omit_body": True}}
        ).status_code
        == 201
    )


def test_startup_recovery_does_not_retry_and_distinguishes_unknown_work(
    client, project, transport, engine
):
    original = capture(client, project, transport)
    s = replay(client, project, [original]).json()
    with Session(engine) as db:
        session = db.get(ReplaySession, UUID(s["id"]))
        session.status = "running"
        session.completed_at = None
        result = session.results[0]
        result.outcome = "running"
        result.response_status = None
        result.response_body = None
        db.commit()
        assert recover_interrupted_sessions(db) == 1
        assert session.status == "interrupted"
        assert session.results[0].outcome == "interrupted"
        assert session.results[0].execution_error["code"] == "execution_interrupted"
        assert recover_interrupted_sessions(db) == 0


def test_validation_does_not_echo_secrets_in_locations(client, project, transport):
    original = capture(client, project, transport)
    r = replay(
        client,
        project,
        [original],
        overrides={"credential-that-must-not-echo": {"body": {}}},
    )
    assert r.status_code == 422 and "credential-that-must-not-echo" not in r.text


def test_read_missing_and_config(client):
    for path in ["/api/replay-sessions/", "/api/replay-results/"]:
        assert client.get(path + str(uuid4())).status_code == 404
    c = client.get("/api/replay-config").json()
    assert c["execution_mode"] == "synchronous_sequential" and c["max_batch_size"] == 10

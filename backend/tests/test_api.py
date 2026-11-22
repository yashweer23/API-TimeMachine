import json
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Recording
from conftest import mock_response


def send(client, project, **data):
    return client.post(
        f"/api/projects/{project['id']}/requests/send",
        json={"method": "GET", "endpoint_path": "/users", **data},
    )


def test_project_create_list_retrieve_update(client, project):
    assert client.get("/api/projects").json()[0]["id"] == project["id"]
    assert client.get(f"/api/projects/{project['id']}").json()["name"] == "Commerce"
    updated = client.patch(
        f"/api/projects/{project['id']}", json={"name": "New name", "description": "v1"}
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "v1"
    assert (
        client.patch(
            f"/api/projects/{project['id']}",
            json={"base_url": "https://unapproved.test"},
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/api/projects/{project['id']}", json={"name": None}).status_code
        == 422
    )


def test_health_and_not_found(client):
    assert client.get("/api/health").json()["database"] == "connected"
    assert client.get(f"/api/projects/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/api/recordings/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/recordings/not-a-uuid").status_code == 422


def test_get_persists_json_and_original_base(client, project, transport, engine):
    def handler(request):
        assert request.url.host == "8.8.8.8"
        assert request.url.path == "/v1/users"
        assert request.headers["host"] == "api.example.test"
        assert request.extensions["sni_hostname"] == "api.example.test"
        assert request.url.params.get_list("tag") == ["a", "b"]
        return mock_response(
            body={"data": [1, True, None, {"number": 42.5}], "total": 4}
        )

    transport(handler)
    response = send(client, project, query_parameters={"tag": ["a", "b"]})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["response_body"]["data"] == [1, True, None, {"number": 42.5}]
    assert data["response_status"] == 200 and data["execution_error"] is None
    assert data["base_url"] == "https://api.example.test/v1"
    assert data["duration_ms"] >= 0
    assert data["captured_at"].endswith("Z")
    with Session(engine) as db:
        stored = db.scalar(select(Recording))
        assert stored.response_body == data["response_body"]
    assert (
        client.get(f"/api/recordings/{data['id']}").json()["response_body"]
        == data["response_body"]
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_json_methods(client, project, transport, method):
    body = {"nested": {"enabled": False, "tags": ["a", None]}, "zero": 0}

    def handler(request):
        assert request.method == method
        assert json.loads(request.content) == body
        return mock_response(201, body={"received": body})

    transport(handler)
    response = send(
        client, project, method=method, endpoint_path="/echo", body=body
    ).json()
    assert response["request_body"] == body
    assert response["response_body"]["received"] == body


@pytest.mark.parametrize("body", [None, False, 0, [1, {"a": True}], "hello"])
def test_json_scalars_preserved(client, project, transport, body):
    transport(lambda r: mock_response(raw=json.dumps(body).encode()))
    result = send(client, project).json()
    assert result["response_body"] == body
    assert result["response_body_kind"] == "json"


def test_http_error_is_real_response(client, project, transport):
    transport(lambda r: mock_response(404, {"detail": "Not found"}))
    result = send(client, project).json()
    assert result["response_status"] == 404
    assert result["execution_error"] is None
    assert result["response_body"]["detail"] == "Not found"


@pytest.mark.parametrize(
    "exception,code",
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection_error")],
)
def test_network_failure_is_persisted(client, project, transport, exception, code):
    def handler(request):
        raise exception("Do not leak token=super-secret", request=request)

    transport(handler)
    result = send(client, project).json()
    assert result["response_status"] is None
    assert result["response_body"] is None
    assert result["execution_error"]["code"] == code
    assert "super-secret" not in json.dumps(result)
    assert (
        client.get(f"/api/recordings/{result['id']}").json()["execution_error"]["code"]
        == code
    )
    assert (
        client.patch(
            f"/api/recordings/{result['id']}", json={"is_baseline": True}
        ).status_code
        == 409
    )


def test_redacts_sensitive_headers_query_nested_body_and_echoes(
    client, project, transport
):
    def handler(request):
        assert request.headers["authorization"] == "Bearer super-secret-token"
        assert json.loads(request.content)["password"] == "private-password"
        return mock_response(
            body={
                "token": "returned-secret",
                "arbitrary": "super-secret-token",
                "nested": [{"password": "private-password"}, {"ssn": "111-22-3333"}],
            },
            headers={
                "content-type": "application/json",
                "set-cookie": "session=cookie-secret; HttpOnly",
                "x-api-key": "returned-secret",
            },
        )

    transport(handler)
    result = send(
        client,
        project,
        method="POST",
        headers={
            "Authorization": "Bearer super-secret-token",
            "Cookie": "session=cookie-secret",
            "X-API-Key": "key-secret",
        },
        query_parameters={"api_key": "query-secret"},
        body={
            "password": "private-password",
            "nested": [{"accessToken": "nested-secret"}],
        },
    ).json()
    for secret in [
        "super-secret-token",
        "private-password",
        "cookie-secret",
        "key-secret",
        "query-secret",
        "nested-secret",
        "returned-secret",
        "111-22-3333",
    ]:
        assert secret not in json.dumps(result)
    assert result["request_headers"]["authorization"] == "[REDACTED]"
    assert result["response_body"]["arbitrary"] == "[REDACTED]"


def test_text_response_redacted(client, project, transport):
    transport(
        lambda r: mock_response(
            headers={"content-type": "text/plain"},
            raw=b"Hello. token=abcdef Bearer xyz123 password=secretpass",
        )
    )
    result = send(client, project).json()
    assert result["response_body_kind"] == "text"
    for secret in ["abcdef", "xyz123", "secretpass"]:
        assert secret not in result["response_body"]


def test_rename_baseline_label_list_pagination(client, project, transport):
    transport(lambda r: mock_response())
    first = send(client, project).json()
    second = send(client, project).json()
    assert (
        client.patch(
            f"/api/recordings/{first['id']}",
            json={
                "name": "Stable users v1",
                "is_baseline": True,
                "environment_label": "v1",
            },
        ).status_code
        == 200
    )
    page = client.get(f"/api/projects/{project['id']}/recordings?baseline=true").json()
    assert page["total"] == 1 and page["items"][0]["name"] == "Stable users v1"
    assert "response_body" not in page["items"][0]
    page = client.get(
        f"/api/projects/{project['id']}/recordings?limit=1&offset=0"
    ).json()
    assert page["total"] == 2 and page["items"][0]["id"] == second["id"]
    assert (
        client.patch(
            f"/api/recordings/{first['id']}", json={"response_status": 200}
        ).status_code
        == 422
    )


def test_response_size_limit(client, project, transport):
    transport(lambda r: mock_response(raw=b'"' + b"x" * 2048 + b'"'))
    result = send(client, project).json()
    assert result["response_status"] == 200
    assert result["response_body"] is None
    assert result["execution_error"]["code"] == "response_too_large"


def test_redirect_not_followed(client, project, transport):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return mock_response(
            302,
            headers={"location": "http://169.254.169.254/latest/meta-data"},
            raw=b"",
        )

    transport(handler)
    result = send(client, project).json()
    assert len(calls) == 1
    assert result["response_status"] == 302


@pytest.mark.parametrize(
    "headers,raw,code",
    [
        ({"content-type": "application/json"}, b"not json", "invalid_json_response"),
        ({"content-type": "application/json"}, b'{"x":NaN}', "invalid_json_response"),
        ({"content-type": "application/json"}, b'{"x":1e999}', "invalid_json_response"),
        (
            {"content-type": "application/json", "content-encoding": "gzip"},
            b"compressed",
            "unsupported_encoding",
        ),
        ({"content-type": "image/png"}, b"png-data", "unsupported_content_type"),
    ],
)
def test_incomplete_captures_explicit(client, project, transport, headers, raw, code):
    transport(lambda r: mock_response(headers=headers, raw=raw))
    result = send(client, project).json()
    assert result["response_body_kind"] == "omitted"
    assert result["execution_error"]["code"] == code


def test_empty_response(client, project, transport):
    transport(lambda r: mock_response(204, raw=b""))
    result = send(client, project).json()
    assert result["response_status"] == 204 and result["response_body_kind"] == "empty"


def test_origin_and_body_guard(client, project):
    url = f"/api/projects/{project['id']}/requests/send"
    assert (
        client.post(
            url,
            json={"endpoint_path": "/users"},
            headers={"origin": "https://evil.test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, content="hello", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    assert client.post(url, json={"body": "a" * 5000}).status_code == 413
    invalid = client.post(
        url,
        json={
            "endpoint_path": "/users",
            "headers": {"Authorization": "secret\r\nvalue"},
        },
    )
    assert invalid.status_code == 422 and "secret" not in invalid.text


def test_blocked_ip_saved(client, project, app, monkeypatch):
    async def resolve(*args):
        return ["169.254.169.254"]

    monkeypatch.setattr(app.state.policy, "resolve", resolve)
    result = send(client, project).json()
    assert result["response_status"] is None
    assert result["execution_error"]["code"] == "target_blocked"


@pytest.mark.parametrize(
    "raw", [b'{"a":"\\u0000"}', b'{"a":"\\ud800"}', b"[" * 70 + b"0" + b"]" * 70]
)
def test_jsonb_incompatible_response_is_saved_as_failure(
    client, project, transport, raw
):
    transport(lambda r: mock_response(raw=raw))
    result = send(client, project).json()
    assert result["response_status"] == 200
    assert result["execution_error"]["code"] == "invalid_json_response"


def test_incompatible_input_rejected_before_send(client, project):
    response = send(client, project, body={"a": "\u0000"})
    assert response.status_code == 422

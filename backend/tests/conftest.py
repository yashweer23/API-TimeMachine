import json
import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.session import Base, get_db
from app.main import create_app
from app.services.recorder import Recorder


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        recover_replays_on_startup=False,
        allowed_target_origins="https://api.example.test",
        dev_private_origins="",
        dev_private_cidrs="",
        total_timeout_seconds=1,
        read_timeout_seconds=0.1,
        connect_timeout_seconds=0.1,
        max_response_bytes=1024,
        max_request_bytes=4096,
        redact_fields="ssn",
        trusted_hosts="testserver",
    )


@pytest.fixture
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        admin = create_engine(url)
        schema = "test_" + uuid.uuid4().hex
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        database = create_engine(
            url, execution_options={"schema_translate_map": {None: schema}}
        )
    else:
        database = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.create_all(database)
    yield database
    database.dispose()
    if url:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def app(settings, engine, monkeypatch):
    app = create_app(settings)

    def override_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = override_db

    async def resolve(host, port):
        return ["8.8.8.8"]

    monkeypatch.setattr(app.state.policy, "resolve", resolve)
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def project(client):
    response = client.post(
        "/api/projects",
        json={"name": "Commerce", "base_url": "https://api.example.test/v1"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def mock_response(status=200, body=None, headers=None, raw=None):
    encoded = (
        raw
        if raw is not None
        else json.dumps(body if body is not None else {"ok": True}).encode()
    )
    return httpx.Response(
        status,
        headers=headers or {"content-type": "application/json"},
        stream=httpx.ByteStream(encoded),
    )


@pytest.fixture
def transport(app, settings):
    def install(handler):
        def factory(**kwargs):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

        app.state.recorder = Recorder(settings, app.state.policy, factory)

    return install

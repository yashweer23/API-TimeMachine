import asyncio
import pytest
from app.core.config import Settings
from app.core.security import TargetPolicy, TargetRejected, normalize_base_url
from app.schemas.api import SendRequest


@pytest.mark.parametrize(
    "url",
    [
        "https://not-approved.test",
        "https://api.example.test:444",
        "http://api.example.test",
        "https://api.example.test.evil.com",
        "https://api.example.test@evil.test",
        "file:///etc/passwd",
        "http://user:password@api.example.test",
        "http://api.example.test?q=token",
        "http://api.example.test/#fragment",
        "http://api.example.test:0",
    ],
)
def test_unapproved_targets(client, url):
    assert client.post(
        "/api/projects", json={"name": "Test", "base_url": url}
    ).status_code in {403, 422}


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.test",
        "//evil.test",
        "/%2fexample.test",
        "/\\evil.test",
        "/../admin",
        "/%2e%2e/admin",
        "/a?token=1",
        "/a#fragment",
        "/%0d%0aHost:evil",
    ],
)
def test_paths_cannot_override_origin(path):
    with pytest.raises(ValueError):
        SendRequest(endpoint_path=path)


@pytest.mark.parametrize(
    "key",
    [
        "Host",
        "Content-Length",
        "Transfer-Encoding",
        "Accept-Encoding",
        "Connection",
        "Proxy-Authorization",
    ],
)
def test_transport_header_override_rejected(key):
    with pytest.raises(ValueError):
        SendRequest(endpoint_path="/users", headers={key: "x"})


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["::1"],
        ["169.254.169.254"],
        ["0.0.0.0"],
        ["10.0.0.1"],
        ["224.0.0.1"],
        ["8.8.8.8", "127.0.0.1"],
        ["::ffff:127.0.0.1"],
    ],
)
async def test_blocked_dns_results(settings, monkeypatch, addresses):
    policy = TargetPolicy(settings)

    async def resolve(*args):
        return addresses

    monkeypatch.setattr(policy, "resolve", resolve)
    with pytest.raises(TargetRejected):
        await policy.destination("https://api.example.test", "/users")


async def test_development_private_exception_is_exact(monkeypatch):
    settings = Settings(
        _env_file=None,
        allowed_target_origins="http://sample-api:8001,http://other-api:8001",
        dev_private_origins="http://sample-api:8001",
        dev_private_cidrs="172.20.0.0/16",
    )
    policy = TargetPolicy(settings)

    async def resolve(*args):
        return ["172.20.0.4"]

    monkeypatch.setattr(policy, "resolve", resolve)
    dest = await policy.destination("http://sample-api:8001", "/users")
    assert dest.url.host == "172.20.0.4" and dest.host_header == "sample-api:8001"
    with pytest.raises(TargetRejected):
        await policy.destination("http://other-api:8001", "/users")


async def test_metadata_cannot_be_allowed_even_by_dev_config(monkeypatch):
    settings = Settings(
        _env_file=None,
        allowed_target_origins="http://sample-api:8001",
        dev_private_origins="http://sample-api:8001",
        dev_private_cidrs="0.0.0.0/0",
    )
    policy = TargetPolicy(settings)

    async def resolve(*args):
        return ["169.254.169.254"]

    monkeypatch.setattr(policy, "resolve", resolve)
    with pytest.raises(TargetRejected):
        await policy.destination("http://sample-api:8001", "/")


def test_total_deadline_even_if_transport_never_completes(
    client, project, app, settings, transport
):
    import httpx

    settings.total_timeout_seconds = 0.02

    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    transport(handler)
    result = client.post(
        f"/api/projects/{project['id']}/requests/send", json={"endpoint_path": "/slow"}
    ).json()
    assert result["execution_error"]["code"] == "timeout"


def test_base_path_preserved():
    assert (
        normalize_base_url("https://api.example.test/v1/")
        == "https://api.example.test/v1"
    )

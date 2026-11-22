import asyncio
import json
import time
from collections.abc import Callable

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.execution_limits import ExecutionRateLimiter
from app.core.json_safety import validate_json_value
from app.core.redaction import Redactor
from app.core.security import TargetPolicy, TargetRejected
from app.models.entities import Project, Recording, utcnow
from app.schemas.api import SendRequest


class CaptureError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


class Recorder:
    def __init__(
        self,
        settings: Settings,
        policy: TargetPolicy,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ):
        self.settings = settings
        self.policy = policy
        self.client_factory = client_factory
        self.slots = asyncio.Semaphore(settings.max_concurrent_requests)
        self.rate_limiter = ExecutionRateLimiter(settings.max_executions_per_minute)

    async def send(self, db: Session, project: Project, data: SendRequest) -> Recording:
        record = await self.capture(project, data)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    async def capture(
        self,
        project: Project,
        data: SendRequest,
        *,
        redactor: Redactor | None = None,
        deadline_seconds: float | None = None,
    ) -> Recording:
        """Execute once and return a transient sanitized capture; caller owns persistence."""
        redactor = redactor or Redactor(self.settings.csv(self.settings.redact_fields))
        headers = {key.lower(): value for key, value in data.headers.items()}
        redactor.collect(headers)
        redactor.collect(data.query_parameters)
        redactor.collect(data.body)
        record = Recording(
            project_id=project.id,
            name=data.name or f"{data.method} {data.endpoint_path}",
            method=data.method,
            base_url=project.base_url,
            endpoint_path=data.endpoint_path,
            query_parameters=redactor.clean(data.query_parameters),
            request_headers=redactor.clean(headers),
            request_body=redactor.clean(data.body),
            request_body_present="body" in data.model_fields_set,
            captured_at=utcnow(),
            environment_label=data.environment_label,
            response_headers={},
            response_body=None,
            response_body_kind="empty",
            is_baseline=False,
        )
        started = time.perf_counter()
        try:
            if not self.rate_limiter.admit():
                raise CaptureError(
                    "execution_rate_limited",
                    "Local execution rate limit reached. No request was sent. Wait for the one-minute window before retrying.",
                )
            # Deadline includes queue, DNS, connection, headers, and the entire streamed body.
            async with asyncio.timeout(
                min(self.settings.total_timeout_seconds, deadline_seconds)
                if deadline_seconds is not None
                else self.settings.total_timeout_seconds
            ):
                async with self.slots:
                    destination = await self.policy.destination(
                        project.base_url, data.endpoint_path
                    )
                    headers.update(
                        {"host": destination.host_header, "accept-encoding": "identity"}
                    )
                    options = (
                        {
                            "content": json.dumps(
                                data.body, ensure_ascii=False, allow_nan=False
                            ).encode("utf-8")
                        }
                        if "body" in data.model_fields_set
                        else {}
                    )
                    if options:
                        headers.setdefault("content-type", "application/json")
                    async with self.client_factory(
                        trust_env=False,
                        follow_redirects=False,
                        timeout=httpx.Timeout(
                            self.settings.read_timeout_seconds,
                            connect=self.settings.connect_timeout_seconds,
                        ),
                    ) as client:
                        async with client.stream(
                            data.method,
                            destination.url,
                            headers=headers,
                            params=data.query_parameters,
                            extensions={"sni_hostname": destination.tls_hostname},
                            **options,
                        ) as response:
                            record.response_status = response.status_code
                            response_headers = {}
                            for key, value in response.headers.multi_items():
                                if key not in response_headers:
                                    response_headers[key] = value
                                elif isinstance(response_headers[key], list):
                                    response_headers[key].append(value)
                                else:
                                    response_headers[key] = [
                                        response_headers[key],
                                        value,
                                    ]
                            redactor.collect(response_headers)
                            record.response_headers = redactor.clean(response_headers)
                            record.content_type = redactor.text(
                                response.headers.get("content-type", "")
                            )[:255]
                            if response.headers.get(
                                "content-encoding", "identity"
                            ).lower() not in {"identity", ""}:
                                raise CaptureError(
                                    "unsupported_encoding",
                                    "Target ignored Accept-Encoding: identity. Compressed capture is not supported in this version.",
                                )
                            raw = bytearray()
                            async for chunk in response.aiter_raw():
                                if (
                                    len(raw) + len(chunk)
                                    > self.settings.max_response_bytes
                                ):
                                    raise CaptureError(
                                        "response_too_large",
                                        "Response exceeded the capture limit; no partial body was saved.",
                                    )
                                raw.extend(chunk)
                            if raw:
                                media_type = (
                                    record.content_type.split(";", 1)[0].lower().strip()
                                )
                                if (
                                    media_type == "application/json"
                                    or media_type.endswith("+json")
                                ):
                                    try:

                                        def invalid_constant(value):
                                            raise ValueError("Non-finite JSON number")

                                        body = json.loads(
                                            raw, parse_constant=invalid_constant
                                        )
                                        validate_json_value(body)
                                        # Confirm finite numbers also for overflow such as 1e999.
                                        json.dumps(body, allow_nan=False)
                                    except (
                                        ValueError,
                                        UnicodeDecodeError,
                                        RecursionError,
                                    ):
                                        raise CaptureError(
                                            "invalid_json_response",
                                            "Target returned invalid, excessively nested, or JSONB-incompatible JSON.",
                                        )
                                    redactor.collect(body)
                                    record.response_body = redactor.clean(body)
                                    record.response_body_kind = "json"
                                elif media_type.startswith("text/") or media_type in {
                                    "application/xml",
                                    "application/javascript",
                                    "",
                                }:
                                    try:
                                        decoded = bytes(raw).decode(
                                            response.encoding or "utf-8",
                                            errors="replace",
                                        )
                                    except LookupError:
                                        decoded = bytes(raw).decode(
                                            "utf-8", errors="replace"
                                        )
                                    try:
                                        validate_json_value(decoded)
                                    except ValueError:
                                        raise CaptureError(
                                            "invalid_text_response",
                                            "Target returned text that cannot be stored in JSONB.",
                                        )
                                    record.response_body = redactor.text(decoded)
                                    record.response_body_kind = "text"
                                else:
                                    raise CaptureError(
                                        "unsupported_content_type",
                                        "Only JSON and text response bodies can be captured in this version.",
                                    )
                            # Scrub secrets discovered in response JSON from headers and other fields too.
                            record.response_headers = redactor.clean(response_headers)
        except TargetRejected as exc:
            record.execution_error = {"code": "target_blocked", "message": str(exc)}
        except (TimeoutError, httpx.TimeoutException):
            record.execution_error = {
                "code": "timeout",
                "message": "Target did not complete within the configured timeout.",
            }
        except CaptureError as exc:
            record.execution_error = {"code": exc.code, "message": exc.message}
            record.response_body_kind = "omitted"
        except (httpx.RequestError, OSError):
            # Do not persist raw exceptions: they may contain credentials or request URLs.
            record.execution_error = {
                "code": "connection_error",
                "message": "Target could not be reached or the connection was interrupted. Check the service, DNS, and TLS configuration.",
            }
        except (httpx.InvalidURL, ValueError):
            record.execution_error = {
                "code": "invalid_request",
                "message": "The request could not be encoded as a valid HTTP request.",
            }
        if record.execution_error:
            record.response_body = None
            record.response_body_kind = "omitted"
        record.name = redactor.text(record.name)[:160]
        record.environment_label = (
            redactor.text(record.environment_label)[:80]
            if record.environment_label
            else None
        )
        record.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record.base_url = redactor.text(record.base_url)[:2048]
        record.endpoint_path = redactor.text(record.endpoint_path)[:2048]
        # Also scrub incoming secrets that were discovered after the request snapshot.
        record.request_headers = redactor.clean(record.request_headers)
        record.query_parameters = redactor.clean(record.query_parameters)
        record.request_body = redactor.clean(record.request_body)
        return record

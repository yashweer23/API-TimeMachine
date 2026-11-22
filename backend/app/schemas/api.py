import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from app.core.security import normalize_base_url, validate_path
from app.core.json_safety import validate_json_value


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    @model_validator(mode="after")
    def storage_compatible(self):
        validate_json_value(self.model_dump())
        return self


class ProjectCreate(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_url: str = Field(max_length=2048)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank.")
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def base(cls, value):
        return normalize_base_url(value)


class ProjectPatch(ProjectCreate):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="before")
    @classmethod
    def no_null_required(cls, data):
        if any(key in data and data[key] is None for key in ("name", "base_url")):
            raise ValueError("Name and base URL cannot be null.")
        return data


class ORMOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "created_at",
        "updated_at",
        "captured_at",
        "started_at",
        "completed_at",
        "executed_at",
        "compared_at",
        "analyzed_at",
        check_fields=False,
    )
    @classmethod
    def utc(cls, value):
        return (
            value.replace(tzinfo=timezone.utc)
            if value is not None and value.tzinfo is None
            else value
        )


class ProjectOut(ORMOutput):
    id: UUID
    name: str
    description: str | None
    base_url: str
    created_at: datetime
    updated_at: datetime


class SendRequest(Input):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    endpoint_path: str = Field(min_length=1, max_length=2048)
    headers: dict[str, str] = Field(default_factory=dict, max_length=100)
    query_parameters: dict[str, str | list[str]] = Field(
        default_factory=dict, max_length=100
    )
    body: JsonValue = None
    name: str | None = Field(default=None, max_length=160)
    environment_label: str | None = Field(default=None, max_length=80)

    @field_validator("endpoint_path")
    @classmethod
    def relative_path(cls, value):
        return validate_path(value)

    @field_validator("headers")
    @classmethod
    def valid_headers(cls, values):
        forbidden = {
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "upgrade",
            "proxy-authorization",
            "proxy-connection",
            "accept-encoding",
            "te",
            "trailer",
            "expect",
        }
        for key, value in values.items():
            if (
                not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
                or key.lower() in forbidden
            ):
                raise ValueError("Invalid or transport-controlled header name.")
            if any(ord(c) < 32 or ord(c) > 126 for c in value):
                raise ValueError("Header values must be printable ASCII.")
        if len({key.lower() for key in values}) != len(values):
            raise ValueError("Duplicate header names are not allowed.")
        return values


class RecordingPatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    environment_label: str | None = Field(default=None, max_length=80)
    is_baseline: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def valid_patch(cls, data):
        if any(key in data and data[key] is None for key in ("name", "is_baseline")):
            raise ValueError("Name and baseline cannot be null.")
        if "name" in data and not data["name"].strip():
            raise ValueError("Name cannot be blank.")
        return data


class RecordingSummary(ORMOutput):
    id: UUID
    project_id: UUID
    name: str
    method: str
    endpoint_path: str
    response_status: int | None
    duration_ms: float
    captured_at: datetime
    environment_label: str | None
    is_baseline: bool
    execution_error: dict | None


class RecordingOut(RecordingSummary):
    base_url: str
    query_parameters: dict
    request_headers: dict
    request_body: JsonValue
    request_body_present: bool | None
    response_headers: dict
    response_body: JsonValue
    response_body_kind: str
    content_type: str | None


class RecordingPage(BaseModel):
    items: list[RecordingSummary]
    total: int
    limit: int
    offset: int

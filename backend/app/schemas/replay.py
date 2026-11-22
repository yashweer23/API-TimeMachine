from datetime import datetime
from uuid import UUID
from pydantic import Field, JsonValue, field_validator, model_validator
from app.core.security import normalize_base_url
from app.schemas.api import Input, ORMOutput, RecordingOut, SendRequest


class ReplayOverride(Input):
    headers: dict[str, str | None] = Field(default_factory=dict, max_length=100)
    query_parameters: dict[str, str | list[str]] | None = Field(
        default=None, max_length=100
    )
    body: JsonValue = None
    omit_body: bool = False

    @model_validator(mode="after")
    def valid_override(self):
        SendRequest.valid_headers(
            {k: "" if v is None else v for k, v in self.headers.items()}
        )
        if self.omit_body and "body" in self.model_fields_set:
            raise ValueError("Choose body replacement or omit_body, not both.")
        return self


class ReplayOptions(Input):
    name: str = Field(default="Replay session", min_length=1, max_length=160)
    target_base_url: str = Field(max_length=2048)
    temporary_headers: dict[str, str] = Field(
        default_factory=dict, max_length=100, repr=False
    )
    confirm_side_effects: bool = False

    @field_validator("name")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Session name cannot be blank.")
        return value.strip()

    @field_validator("target_base_url")
    @classmethod
    def target(cls, value):
        return normalize_base_url(value)

    @field_validator("temporary_headers")
    @classmethod
    def headers(cls, value):
        return SendRequest.valid_headers(value)


class ReplayCreate(ReplayOptions):
    recording_ids: list[UUID] = Field(min_length=1, max_length=25)
    overrides: dict[UUID, ReplayOverride] = Field(
        default_factory=dict, max_length=25, repr=False
    )

    @model_validator(mode="after")
    def valid_selection(self):
        if len(set(self.recording_ids)) != len(self.recording_ids):
            raise ValueError("Select each recording only once.")
        if not set(self.overrides).issubset(set(self.recording_ids)):
            raise ValueError("Overrides must refer to selected recording IDs.")
        return self


class ReplaySingle(ReplayOptions):
    override: ReplayOverride = Field(default_factory=ReplayOverride, repr=False)


class ReplaySessionOut(ORMOutput):
    id: UUID
    project_id: UUID
    name: str
    target_base_url: str
    status: str
    total_requests: int
    completed_requests: int
    failed_requests: int
    error_requests: int
    http_responses: int
    skipped_requests: int
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float


class ReplayResultSummary(ORMOutput):
    id: UUID
    replay_session_id: UUID
    original_recording_id: UUID
    ordinal: int
    request_method: str
    endpoint_path: str
    replay_url: str
    outcome: str
    response_status: int | None
    duration_ms: float
    execution_error: dict | None
    executed_at: datetime | None


class ReplayResultOut(ReplayResultSummary):
    request_metadata: dict
    response_headers: dict
    response_body: JsonValue
    response_body_kind: str
    content_type: str | None
    original_recording: RecordingOut


class ReplaySessionDetail(ReplaySessionOut):
    results: list[ReplayResultSummary]


class ReplaySessionPage(Input):
    items: list[ReplaySessionOut]
    total: int
    limit: int
    offset: int

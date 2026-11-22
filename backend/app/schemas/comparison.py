"""Canonical, exact JSON Pointer rules. No expression evaluation or wildcards."""

import hashlib
import json
import re
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator
from app.schemas.api import Input, ORMOutput

DEFAULT_IGNORED_HEADERS = [
    "date",
    "server-timing",
    "x-request-id",
    "x-correlation-id",
    "x-trace-id",
    "traceparent",
    "tracestate",
]


def pointer_tokens(value: str) -> list[str]:
    if value == "":
        return []
    if not value.startswith("/") or re.search(r"~(?![01])", value):
        raise ValueError(
            "Use exact JSON Pointer paths: /profile/city; escape ~ as ~0 and / as ~1. Empty path means the root."
        )
    tokens = [t.replace("~1", "/").replace("~0", "~") for t in value[1:].split("/")]
    if len(tokens) > 64 or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError(
            "Path exceeds the length/depth limit or contains control characters."
        )
    return tokens


def child_pointer(path: str, key: str | int) -> str:
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


class ComparisonRules(Input):
    ignored_json_paths: list[str] = Field(default_factory=list, max_length=50)
    ignored_headers: list[str] = Field(
        default_factory=lambda: sorted(DEFAULT_IGNORED_HEADERS), max_length=50
    )
    unordered_array_paths: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("ignored_json_paths", "unordered_array_paths")
    @classmethod
    def paths(cls, values):
        for value in values:
            pointer_tokens(value)
        return sorted(set(values))

    @field_validator("ignored_headers")
    @classmethod
    def headers(cls, values):
        if any(
            len(v) > 200 or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", v)
            for v in values
        ):
            raise ValueError("Ignored headers must be valid HTTP header names.")
        return sorted({v.lower() for v in values})

    @model_validator(mode="after")
    def no_ambiguous_array_rules(self):
        for array in self.unordered_array_paths:
            if any(
                p.startswith(array + "/")
                for p in self.ignored_json_paths + self.unordered_array_paths
            ):
                raise ValueError(
                    "Rules inside an unordered array are ambiguous. Ignore the whole array or use index-based comparison."
                )
        return self

    def fingerprint(self):
        return hashlib.sha256(
            json.dumps(
                self.model_dump(), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()


class CompareRequest(Input):
    rules: ComparisonRules | None = None


class RulesOut(ORMOutput):
    project_id: UUID
    rules: ComparisonRules
    rules_hash: str
    updated_at: datetime | None


class DifferenceOut(ORMOutput):
    id: UUID
    ordinal: int
    scope: str
    path: str
    change_type: str
    old_type: str
    new_type: str
    old_present: bool
    new_present: bool
    old_value: JsonValue
    new_value: JsonValue
    old_preview: str
    new_preview: str
    old_value_truncated: bool
    new_value_truncated: bool


class ComparisonSummary(ORMOutput):
    id: UUID
    replay_result_id: UUID
    comparison_status: str
    original_status_code: int | None
    replay_status_code: int | None
    total_differences: int
    counts: dict[str, int]
    effective_rules: ComparisonRules
    rules_hash: str
    algorithm_version: str
    compared_at: datetime
    notes: list[str]
    is_current: bool = True
    project_id: UUID
    replay_session_id: UUID
    session_name: str
    recording_name: str
    request_method: str
    endpoint_path: str


class ComparisonDetail(ComparisonSummary):
    differences: list[DifferenceOut]


class ComparisonPage(BaseModel):
    items: list[ComparisonSummary]
    total: int
    limit: int
    offset: int


class SessionComparisons(BaseModel):
    session_id: UUID
    project_id: UUID
    session_name: str
    total_requests: int
    pending_requests: int
    items: list[ComparisonSummary]
    totals: dict[str, int]


class DifferenceValues(BaseModel):
    old_present: bool
    new_present: bool
    old_value: JsonValue
    new_value: JsonValue

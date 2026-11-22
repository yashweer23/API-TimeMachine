"""Small explicit endpoint contracts. Paths are exact RFC 6901 JSON Pointers."""

import hashlib
import json
import re
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator
from app.core.security import validate_path
from app.schemas.api import Input, ORMOutput
from app.schemas.comparison import pointer_tokens, ComparisonRules

Classification = Literal[
    "confirmed_breaking", "potentially_breaking", "informational", "unassessed"
]
Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]
Verdict = Literal[
    "compatible_under_configured_policy",
    "potential_compatibility_issues",
    "incompatible_with_configured_contract",
    "insufficient_evidence",
]
FieldType = Literal["object", "array", "string", "number", "integer", "boolean", "null"]


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


class EndpointPolicy(Input):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    endpoint_path: str = Field(min_length=1, max_length=2048)
    expected_status_codes: list[int] = Field(default_factory=list, max_length=100)
    required_json_paths: list[str] = Field(default_factory=list, max_length=50)
    expected_types: dict[str, FieldType] = Field(default_factory=dict, max_length=50)
    required_headers: list[str] = Field(default_factory=list, max_length=50)
    allowed_content_types: list[str] = Field(default_factory=list, max_length=20)
    allow_additional_fields: bool | None = None
    dynamic_json_paths: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("endpoint_path")
    @classmethod
    def endpoint(cls, value):
        return validate_path(value)

    @field_validator("expected_status_codes", mode="before")
    @classmethod
    def statuses(cls, values):
        if not isinstance(values, list) or any(
            type(v) is not int or not 200 <= v <= 299 for v in values
        ):
            raise ValueError(
                "Expected successful status codes must be integers from 200 to 299."
            )
        return sorted(set(values))

    @field_validator("required_json_paths", "dynamic_json_paths")
    @classmethod
    def paths(cls, values):
        for value in values:
            pointer_tokens(value)
        return sorted(set(values))

    @field_validator("expected_types")
    @classmethod
    def types(cls, values):
        for value in values:
            pointer_tokens(value)
        return dict(sorted(values.items()))

    @field_validator("required_headers")
    @classmethod
    def headers(cls, values):
        if any(
            len(v) > 200 or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", v)
            for v in values
        ):
            raise ValueError("Use valid HTTP header names without values.")
        return sorted({v.lower() for v in values})

    @field_validator("allowed_content_types")
    @classmethod
    def mime(cls, values):
        if any(
            len(v) > 200
            or not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", v)
            for v in values
        ):
            raise ValueError(
                "Use exact media types, for example application/json, without parameters or wildcards."
            )
        return sorted({v.lower() for v in values})


class PolicyBundle(Input):
    endpoints: list[EndpointPolicy] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_endpoints(self):
        keys = [(p.method, p.endpoint_path) for p in self.endpoints]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "Each method and exact endpoint path may have only one policy."
            )
        self.endpoints.sort(key=lambda p: (p.method, p.endpoint_path))
        return self


class PolicyOut(ORMOutput):
    project_id: UUID
    policies: PolicyBundle
    policies_hash: str
    updated_at: datetime | None


class FindingOut(ORMOutput):
    id: UUID
    analysis_id: UUID
    difference_id: UUID | None
    comparison_id: UUID
    request_method: str
    endpoint_path: str
    ordinal: int
    scope: str
    path: str
    change_type: str
    classification: Classification
    severity: Severity | None
    confidence: Confidence
    title: str
    explanation: str
    recommended_action: str
    rule_id: str
    evidence: dict


class FindingPage(BaseModel):
    items: list[FindingOut]
    total: int
    limit: int
    offset: int


class AnalysisOut(ORMOutput):
    id: UUID
    project_id: UUID
    replay_session_id: UUID
    comparison_id: UUID
    request_method: str
    endpoint_path: str
    verdict: Verdict
    counts: dict[str, int]
    effective_policy: EndpointPolicy | None
    policy_hash: str
    effective_comparison_rules: ComparisonRules
    comparison_algorithm_version: str
    engine_version: str
    analyzed_at: datetime
    is_current: bool


class RunOut(ORMOutput):
    id: UUID
    project_id: UUID
    replay_session_id: UUID
    engine_version: str
    verdict: Verdict
    summary: dict[str, int]
    metadata_snapshot: dict
    missing_result_ids: list[UUID]
    analyzed_at: datetime
    analyses: list[AnalysisOut]
    is_current: bool


class RunPage(BaseModel):
    items: list[RunOut]
    total: int
    limit: int
    offset: int

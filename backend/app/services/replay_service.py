"""Bounded synchronous replay. No queue, background task, or automatic retry."""

import asyncio
import time
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.redaction import REDACTED, Redactor
from app.core.security import TargetPolicy
from app.models.entities import Project, Recording, utcnow
from app.models.replay import ReplayResult, ReplaySession
from app.schemas.api import SendRequest
from app.schemas.replay import ReplayCreate, ReplayOverride
from app.services.catalog import project_by_id
from app.services.recorder import Recorder

TRANSPORT_CODES = {"timeout", "connection_error"}
FINAL_OUTCOMES = {
    "http_response",
    "transport_error",
    "capture_error",
    "blocked",
    "skipped",
    "interrupted",
}


def has_placeholder(value) -> bool:
    if isinstance(value, str):
        return REDACTED in value
    if isinstance(value, dict):
        return any(has_placeholder(k) or has_placeholder(v) for k, v in value.items())
    if isinstance(value, list):
        return any(has_placeholder(v) for v in value)
    return False


def request_metadata(data: SendRequest, redactor: Redactor) -> dict:
    return {
        "headers": redactor.clean(data.headers),
        "query_parameters": redactor.clean(data.query_parameters),
        "body": redactor.clean(data.body),
        "body_present": "body" in data.model_fields_set,
    }


def reconstruct(
    recording: Recording, override: ReplayOverride, temporary_headers: dict
) -> SendRequest:
    headers = {key.lower(): value for key, value in recording.request_headers.items()}
    for key, value in override.headers.items():
        if value is None:
            headers.pop(key.lower(), None)
        else:
            headers[key.lower()] = value
    headers.update({key.lower(): value for key, value in temporary_headers.items()})
    payload = {
        "method": recording.method,
        "endpoint_path": recording.endpoint_path,
        "headers": headers,
        "query_parameters": override.query_parameters
        if override.query_parameters is not None
        else recording.query_parameters,
    }
    if "body" in override.model_fields_set:
        payload["body"] = override.body
    elif not override.omit_body:
        if recording.request_body_present is None and recording.request_body is None:
            raise HTTPException(
                422,
                f"Recording {recording.id} predates body-presence tracking. Explicitly choose omit_body or provide body (including JSON null).",
            )
        if recording.request_body_present or recording.request_body is not None:
            payload["body"] = recording.request_body
    if has_placeholder(payload):
        raise HTTPException(
            422,
            f"Recording {recording.id} contains masked data. Replace or explicitly remove every [REDACTED] value before replaying.",
        )
    try:
        return SendRequest.model_validate(payload)
    except ValidationError:
        # Never expose effective request values or secret-bearing dictionary keys.
        raise HTTPException(
            422,
            f"Recording {recording.id} could not be reconstructed. Check its header, query, and body overrides.",
        )


def refresh_counts(session: ReplaySession) -> None:
    session.completed_requests = sum(
        r.outcome in FINAL_OUTCOMES for r in session.results
    )
    session.http_responses = sum(r.response_status is not None for r in session.results)
    session.failed_requests = sum(
        r.outcome == "transport_error" for r in session.results
    )
    session.error_requests = sum(r.execution_error is not None for r in session.results)
    session.skipped_requests = sum(r.outcome == "skipped" for r in session.results)


def finish_interrupted(session: ReplaySession) -> None:
    for result in session.results:
        if result.outcome in {"pending", "running"}:
            started = result.outcome == "running"
            result.outcome = "interrupted" if started else "skipped"
            result.execution_error = {
                "code": "execution_interrupted" if started else "not_executed",
                "message": "Execution was interrupted; the target may have processed the request. Inspect it before retrying."
                if started
                else "Session ended before this request was executed.",
            }
            result.response_body_kind = "omitted"
    session.status = "interrupted"
    session.completed_at = utcnow()
    start = session.started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=session.completed_at.tzinfo)
    session.duration_ms = max(0, (session.completed_at - start).total_seconds() * 1000)
    refresh_counts(session)


def recover_interrupted_sessions(db: Session) -> int:
    """One local backend process only. Recover abandoned runs on process startup."""
    sessions = db.scalars(
        select(ReplaySession)
        .where(ReplaySession.status == "running")
        .options(selectinload(ReplaySession.results))
    ).all()
    for session in sessions:
        finish_interrupted(session)
    if sessions:
        db.commit()
    return len(sessions)


class ReplayService:
    def __init__(self, settings: Settings, policy: TargetPolicy):
        self.settings, self.policy = settings, policy
        self.slots = asyncio.Semaphore(settings.replay_max_concurrent_sessions)

    async def run(
        self, db: Session, project_id: UUID, data: ReplayCreate, recorder: Recorder
    ) -> ReplaySession:
        project_by_id(db, project_id)
        target = self.policy.check_origin(data.target_base_url)
        if len(data.recording_ids) > self.settings.replay_max_batch_size:
            raise HTTPException(
                422,
                f"At most {self.settings.replay_max_batch_size} recordings may be replayed in one session.",
            )
        found = {
            r.id: r
            for r in db.scalars(
                select(Recording).where(Recording.id.in_(data.recording_ids))
            ).all()
        }
        if len(found) != len(data.recording_ids):
            raise HTTPException(404, "One or more recordings do not exist.")
        if any(r.project_id != project_id for r in found.values()):
            raise HTTPException(
                403, "Every recording must belong to the selected project."
            )
        if (
            any(r.method != "GET" for r in found.values())
            and not data.confirm_side_effects
        ):
            raise HTTPException(
                409,
                "Confirm side effects before replaying POST, PUT, PATCH, or DELETE requests.",
            )
        redactor = Redactor(self.settings.csv(self.settings.redact_fields))
        redactor.collect_temporary(data.temporary_headers)
        prepared = []
        for record_id in data.recording_ids:
            override = data.overrides.get(record_id, ReplayOverride())
            # Every explicitly supplied override value is transient, not just known key names.
            redactor.collect_temporary(
                override.model_dump(exclude_unset=True, exclude={"omit_body"})
            )
            prepared.append(
                reconstruct(found[record_id], override, data.temporary_headers)
            )
        if self.slots.locked():
            raise HTTPException(
                429, "Replay capacity is full. Wait for an active session to finish."
            )
        await self.slots.acquire()
        session = None
        started = time.perf_counter()
        try:
            session = ReplaySession(
                project_id=project_id,
                name=redactor.text(data.name)[:160],
                target_base_url=redactor.text(target)[:2048],
                status="running",
                total_requests=len(prepared),
                started_at=utcnow(),
                results=[],
            )
            for index, (record_id, request) in enumerate(
                zip(data.recording_ids, prepared)
            ):
                session.results.append(
                    ReplayResult(
                        original_recording_id=record_id,
                        ordinal=index,
                        request_method=request.method,
                        endpoint_path=redactor.text(request.endpoint_path)[:2048],
                        replay_url=redactor.text(target + request.endpoint_path)[:4096],
                        request_metadata=request_metadata(request, redactor),
                        outcome="pending",
                        duration_ms=0,
                        response_headers={},
                        response_body_kind="empty",
                    )
                )
            db.add(session)
            db.commit()  # History and pending rows exist before the first outbound request.
            replay_project = Project(
                id=project_id, name="Transient replay target", base_url=target
            )
            timed_out = False
            for result, request in zip(session.results, prepared):
                remaining = self.settings.replay_session_timeout_seconds - (
                    time.perf_counter() - started
                )
                if remaining <= 0:
                    timed_out = True
                    result.outcome = "skipped"
                    result.execution_error = {
                        "code": "session_deadline",
                        "message": "Session time limit reached before this request could start.",
                    }
                    result.response_body_kind = "omitted"
                else:
                    result.outcome = "running"
                    result.executed_at = utcnow()
                    db.commit()
                    capture = await recorder.capture(
                        replay_project,
                        request,
                        redactor=redactor,
                        deadline_seconds=remaining,
                    )
                    for field in (
                        "response_status",
                        "response_headers",
                        "response_body",
                        "response_body_kind",
                        "content_type",
                        "duration_ms",
                        "execution_error",
                    ):
                        setattr(result, field, getattr(capture, field))
                    result.request_metadata = {
                        "headers": capture.request_headers,
                        "query_parameters": capture.query_parameters,
                        "body": capture.request_body,
                        "body_present": capture.request_body_present,
                    }
                    code = (capture.execution_error or {}).get("code")
                    result.outcome = (
                        "transport_error"
                        if code in TRANSPORT_CODES
                        else "blocked"
                        if code in {"target_blocked", "execution_rate_limited"}
                        else "capture_error"
                        if code
                        else "http_response"
                    )
                    timed_out = timed_out or (
                        time.perf_counter() - started
                        >= self.settings.replay_session_timeout_seconds
                    )
                refresh_counts(session)
                session.duration_ms = round((time.perf_counter() - started) * 1000, 2)
                db.commit()  # Each settled result survives subsequent failures or disconnection.
            session.status = (
                "timed_out"
                if timed_out
                else "completed_with_errors"
                if session.error_requests
                else "completed"
            )
            session.completed_at = utcnow()
            session.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            db.commit()
            db.refresh(session)
            return session
        except SQLAlchemyError:
            db.rollback()
            raise
        except asyncio.CancelledError:
            if session and session.id:
                finish_interrupted(session)
                db.commit()
            raise
        except Exception:
            if session and session.id:
                finish_interrupted(session)
                db.commit()
                return session
            raise
        finally:
            self.slots.release()


def session_by_id(db: Session, session_id: UUID) -> ReplaySession:
    session = db.scalar(
        select(ReplaySession)
        .where(ReplaySession.id == session_id)
        .options(selectinload(ReplaySession.results))
    )
    if not session:
        raise HTTPException(404, "Replay session not found.")
    return session


def result_by_id(db: Session, result_id: UUID) -> ReplayResult:
    result = db.get(ReplayResult, result_id)
    if not result:
        raise HTTPException(404, "Replay result not found.")
    return result


def list_sessions(db: Session, project_id: UUID, limit: int, offset: int):
    project_by_id(db, project_id)
    query = select(ReplaySession).where(ReplaySession.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(ReplaySession.started_at.desc(), ReplaySession.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}

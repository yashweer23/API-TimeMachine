from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.replay import (
    ReplayCreate,
    ReplaySingle,
    ReplaySessionDetail,
    ReplaySessionPage,
    ReplayResultOut,
    ReplayResultSummary,
)
from app.services.catalog import recording_by_id
from app.core.security import TargetRejected
from app.services.replay_service import list_sessions, result_by_id, session_by_id

router = APIRouter(prefix="/api", tags=["Replay"])


@router.get("/replay-config")
def replay_config(request: Request):
    service = request.app.state.replays
    try:
        sample_target = service.policy.check_origin(service.settings.sample_v2_base_url)
    except (TargetRejected, ValueError):
        sample_target = None
    return {
        "sample_v2_base_url": sample_target,
        "allowed_target_origins": sorted(service.policy.allowed),
        "max_batch_size": service.settings.replay_max_batch_size,
        "session_timeout_seconds": service.settings.replay_session_timeout_seconds,
        "execution_mode": "synchronous_sequential",
    }


@router.post(
    "/projects/{project_id}/replay-sessions",
    response_model=ReplaySessionDetail,
    status_code=201,
)
async def create_session(
    project_id: UUID,
    data: ReplayCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    return await request.app.state.replays.run(
        db, project_id, data, request.app.state.recorder
    )


@router.get("/projects/{project_id}/replay-sessions", response_model=ReplaySessionPage)
def sessions(
    project_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_sessions(db, project_id, limit, offset)


@router.get("/replay-sessions/{session_id}", response_model=ReplaySessionDetail)
def session(session_id: UUID, db: Session = Depends(get_db)):
    return session_by_id(db, session_id)


@router.get(
    "/replay-sessions/{session_id}/results", response_model=list[ReplayResultSummary]
)
def results(session_id: UUID, db: Session = Depends(get_db)):
    return session_by_id(db, session_id).results


@router.get("/replay-results/{result_id}", response_model=ReplayResultOut)
def result(result_id: UUID, db: Session = Depends(get_db)):
    return result_by_id(db, result_id)


@router.post(
    "/recordings/{recording_id}/replay",
    response_model=ReplaySessionDetail,
    status_code=201,
)
async def replay_one(
    recording_id: UUID,
    data: ReplaySingle,
    request: Request,
    db: Session = Depends(get_db),
):
    original = recording_by_id(db, recording_id)
    payload = ReplayCreate(
        **data.model_dump(exclude={"override"}),
        recording_ids=[recording_id],
        overrides={recording_id: data.override},
    )
    return await request.app.state.replays.run(
        db, original.project_id, payload, request.app.state.recorder
    )

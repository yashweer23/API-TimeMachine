from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Project
from app.schemas.api import (
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    RecordingOut,
    RecordingPage,
    RecordingPatch,
    SendRequest,
)
from app.services import catalog
from app.core.security import TargetRejected

router = APIRouter(prefix="/api")


@router.get("/health", tags=["System"])
def health(response: Response, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected", "phase": 5}
    except SQLAlchemyError:
        response.status_code = 503
        return {"status": "unavailable", "database": "disconnected", "phase": 5}


@router.get("/config", tags=["System"])
def runtime_config(request: Request):
    recorder = request.app.state.recorder

    def allowed(value):
        try:
            return recorder.policy.check_origin(value)
        except (TargetRejected, ValueError):
            return None

    return {
        "sample_v1_base_url": allowed(recorder.settings.sample_v1_base_url),
        "sample_v2_base_url": allowed(recorder.settings.sample_v2_base_url),
        "max_executions_per_minute": recorder.settings.max_executions_per_minute,
        "deployment_mode": "trusted_local_single_user",
        "version": "1.0.0",
    }


@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["Projects"])
def create_project(
    data: ProjectCreate, request: Request, db: Session = Depends(get_db)
):
    return catalog.create_project(db, data, request.app.state.policy)


@router.get("/projects", response_model=list[ProjectOut], tags=["Projects"])
def projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.created_at.desc())).all()


@router.get("/projects/{project_id}", response_model=ProjectOut, tags=["Projects"])
def project(project_id: UUID, db: Session = Depends(get_db)):
    return catalog.project_by_id(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut, tags=["Projects"])
def patch_project(
    project_id: UUID,
    data: ProjectPatch,
    request: Request,
    db: Session = Depends(get_db),
):
    return catalog.update_project(db, project_id, data, request.app.state.policy)


@router.post(
    "/projects/{project_id}/requests/send",
    response_model=RecordingOut,
    status_code=201,
    tags=["Recordings"],
)
async def send_request(
    project_id: UUID, data: SendRequest, request: Request, db: Session = Depends(get_db)
):
    return await request.app.state.recorder.send(
        db, catalog.project_by_id(db, project_id), data
    )


@router.get(
    "/projects/{project_id}/recordings",
    response_model=RecordingPage,
    tags=["Recordings"],
)
def recordings(
    project_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    baseline: bool | None = None,
    search: str | None = Query(None, max_length=200),
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] | None = None,
    db: Session = Depends(get_db),
):
    return catalog.list_recordings(
        db, project_id, limit, offset, baseline, search, method
    )


@router.get(
    "/recordings/{recording_id}", response_model=RecordingOut, tags=["Recordings"]
)
def recording(recording_id: UUID, db: Session = Depends(get_db)):
    return catalog.recording_by_id(db, recording_id)


@router.patch(
    "/recordings/{recording_id}", response_model=RecordingOut, tags=["Recordings"]
)
def patch_recording(
    recording_id: UUID, data: RecordingPatch, db: Session = Depends(get_db)
):
    return catalog.update_recording(db, recording_id, data)

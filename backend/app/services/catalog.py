from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from app.core.security import TargetPolicy
from app.models.entities import Project, Recording
from app.schemas.api import (
    ProjectCreate,
    ProjectPatch,
    RecordingPatch,
    RecordingSummary,
)


def project_by_id(db: Session, project_id: UUID) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    return project


def recording_by_id(db: Session, recording_id: UUID) -> Recording:
    recording = db.get(Recording, recording_id)
    if not recording:
        raise HTTPException(404, "Recording not found.")
    return recording


def create_project(db: Session, data: ProjectCreate, policy: TargetPolicy):
    project = Project(**data.model_dump())
    project.base_url = policy.check_origin(project.base_url)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(
    db: Session, project_id: UUID, data: ProjectPatch, policy: TargetPolicy
):
    project = project_by_id(db, project_id)
    changes = data.model_dump(exclude_unset=True)
    if "base_url" in changes:
        changes["base_url"] = policy.check_origin(changes["base_url"])
    for key, value in changes.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


def list_recordings(
    db: Session,
    project_id: UUID,
    limit: int,
    offset: int,
    baseline: bool | None,
    search: str | None = None,
    method: str | None = None,
):
    project_by_id(db, project_id)
    filters = [Recording.project_id == project_id]
    if baseline is not None:
        filters.append(Recording.is_baseline == baseline)
    if search:
        filters.append(
            Recording.name.contains(search, autoescape=True)
            | Recording.endpoint_path.contains(search, autoescape=True)
        )
    if method:
        filters.append(Recording.method == method)
    total = db.scalar(select(func.count()).select_from(Recording).where(*filters))
    items = db.scalars(
        select(Recording)
        .options(
            load_only(
                *(getattr(Recording, key) for key in RecordingSummary.model_fields),
                raiseload=True,
            )
        )
        .where(*filters)
        .order_by(Recording.captured_at.desc(), Recording.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def update_recording(db: Session, recording_id: UUID, data: RecordingPatch):
    recording = recording_by_id(db, recording_id)
    if data.is_baseline and recording.execution_error:
        raise HTTPException(409, "A failed or incomplete capture cannot be a baseline.")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(recording, key, value)
    db.commit()
    db.refresh(recording)
    return recording

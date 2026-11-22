from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.comparison import (
    CompareRequest,
    ComparisonDetail,
    ComparisonPage,
    ComparisonRules,
    DifferenceValues,
    RulesOut,
    SessionComparisons,
)
from app.services import comparison_service as service

router = APIRouter(prefix="/api", tags=["Comparisons"])


@router.post("/replay-results/{result_id}/compare", response_model=ComparisonDetail)
def compare(result_id: UUID, data: CompareRequest, db: Session = Depends(get_db)):
    return service.compare_result(db, result_id, data.rules)


@router.get("/replay-results/{result_id}/comparison", response_model=ComparisonDetail)
def latest(result_id: UUID, db: Session = Depends(get_db)):
    return service.latest_for_result(db, result_id)


@router.post("/replay-sessions/{session_id}/compare", response_model=SessionComparisons)
def compare_session(
    session_id: UUID, data: CompareRequest, db: Session = Depends(get_db)
):
    return service.session_comparisons(db, session_id, True, data.rules)


@router.get(
    "/replay-sessions/{session_id}/comparisons", response_model=SessionComparisons
)
def session_comparisons(session_id: UUID, db: Session = Depends(get_db)):
    return service.session_comparisons(db, session_id)


@router.get("/projects/{project_id}/comparison-settings", response_model=RulesOut)
def rules(project_id: UUID, db: Session = Depends(get_db)):
    effective, updated = service.rules_for_project(db, project_id)
    return {
        "project_id": project_id,
        "rules": effective,
        "rules_hash": effective.fingerprint(),
        "updated_at": updated,
    }


@router.put("/projects/{project_id}/comparison-settings", response_model=RulesOut)
def update_rules(
    project_id: UUID, data: ComparisonRules, db: Session = Depends(get_db)
):
    return service.update_rules(db, project_id, data)


@router.get("/projects/{project_id}/comparisons", response_model=ComparisonPage)
def history(
    project_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.history(db, project_id, limit, offset)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonDetail)
def comparison(comparison_id: UUID, db: Session = Depends(get_db)):
    row = service.get_comparison(db, comparison_id)
    current, _ = service.rules_for_project(db, row.replay_result.session.project_id)
    return service.view(row, current, True)


@router.get(
    "/comparisons/{comparison_id}/differences/{difference_id}/values",
    response_model=DifferenceValues,
)
def values(comparison_id: UUID, difference_id: UUID, db: Session = Depends(get_db)):
    return service.full_values(db, comparison_id, difference_id)

from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.api import Input
from app.schemas.compatibility import (
    AnalysisOut,
    Classification,
    FindingPage,
    PolicyBundle,
    PolicyOut,
    RunOut,
    RunPage,
)
from app.services import compatibility_service as service
from app.services import comparison_service
from app.services.replay_service import session_by_id
from app.services.compatibility_reports import render_report

router = APIRouter(prefix="/api", tags=["Compatibility"])


@router.get("/projects/{project_id}/compatibility-policies", response_model=PolicyOut)
def policies(project_id: UUID, db: Session = Depends(get_db)):
    return service.policies_for(db, project_id)


@router.put("/projects/{project_id}/compatibility-policies", response_model=PolicyOut)
def save_policies(project_id: UUID, data: PolicyBundle, db: Session = Depends(get_db)):
    return service.save_policies(db, project_id, data)


@router.post("/comparisons/{comparison_id}/analyze", response_model=AnalysisOut)
def analyze(comparison_id: UUID, data: Input, db: Session = Depends(get_db)):
    return service.analysis_view(db, service.analyze_comparison(db, comparison_id))


@router.get("/comparisons/{comparison_id}/compatibility", response_model=AnalysisOut)
def latest(comparison_id: UUID, db: Session = Depends(get_db)):
    return service.latest_analysis(db, comparison_id)


@router.get("/compatibility-analyses/{analysis_id}", response_model=AnalysisOut)
def analysis(analysis_id: UUID, db: Session = Depends(get_db)):
    return service.analysis_view(db, service.get_analysis(db, analysis_id))


@router.post("/replay-sessions/{session_id}/analyze", response_model=RunOut)
def analyze_session(session_id: UUID, data: Input, db: Session = Depends(get_db)):
    return service.run_view(db, service.analyze_session(db, session_id))


@router.get("/replay-sessions/{session_id}/compatibility", response_model=RunOut)
def session_compatibility(session_id: UUID, db: Session = Depends(get_db)):
    return service.latest_run(db, session_id)


@router.get("/compatibility-runs/{run_id}", response_model=RunOut)
def run(run_id: UUID, db: Session = Depends(get_db)):
    return service.run_view(db, service.get_run(db, run_id))


@router.get("/projects/{project_id}/compatibility-runs", response_model=RunPage)
def history(
    project_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return service.history(db, project_id, limit, offset)


class FindingFilters:
    def __init__(
        self,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
        classification: Classification | None = None,
        severity: Literal["critical", "high", "medium", "low", "unrated"] | None = None,
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] | None = None,
        endpoint: str | None = Query(None, max_length=2048),
        search: str | None = Query(None, max_length=200),
    ):
        self.values = dict(
            limit=limit,
            offset=offset,
            classification=classification,
            severity=severity,
            method=method,
            endpoint=endpoint,
            search=search,
        )


@router.get(
    "/compatibility-analyses/{analysis_id}/findings", response_model=FindingPage
)
def findings(
    analysis_id: UUID,
    filters: FindingFilters = Depends(),
    db: Session = Depends(get_db),
):
    service.get_analysis(db, analysis_id)
    return service.findings_page(db, [analysis_id], **filters.values)


@router.get("/compatibility-runs/{run_id}/findings", response_model=FindingPage)
def run_findings(
    run_id: UUID, filters: FindingFilters = Depends(), db: Session = Depends(get_db)
):
    row = service.get_run(db, run_id)
    return service.findings_page(
        db, [i.analysis_id for i in row.items], **filters.values
    )


@router.get("/compatibility-runs/{run_id}/report")
def report(
    run_id: UUID,
    format: Literal["json", "html"] = "json",
    db: Session = Depends(get_db),
):
    row = service.get_run(db, run_id)
    content, media_type = render_report(db, row, format)
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="compatibility-{row.id}.{format}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
            "Cache-Control": "no-store",
        },
    )


@router.post("/replay-sessions/{session_id}/assess", response_model=RunOut)
def assess_session(session_id: UUID, data: Input, db: Session = Depends(get_db)):
    if session_by_id(db, session_id).status == "running":
        raise HTTPException(
            409, "Finish the replay session before assessing saved evidence."
        )
    comparison_service.session_comparisons(db, session_id, run=True)
    return service.run_view(db, service.analyze_session(db, session_id))

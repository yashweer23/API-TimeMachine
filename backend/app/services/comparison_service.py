"""Persisted comparisons are immutable and deduplicated by result/version/rules."""

from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from app.models.comparison import Comparison, Difference, ProjectComparisonSettings
from app.models.replay import ReplayResult, ReplaySession
from app.schemas.comparison import ComparisonRules
from app.services.catalog import project_by_id
from app.services.comparison_engine import (
    ALGORITHM_VERSION,
    CHANGE_TYPES,
    MISSING,
    Snapshot,
    compare_snapshots,
    resolve,
    safe_snapshot,
)
from app.services.replay_service import session_by_id


def rules_for_project(db: Session, project_id: UUID):
    project_by_id(db, project_id)
    row = db.get(ProjectComparisonSettings, project_id)
    rules = ComparisonRules.model_validate(row.rules) if row else ComparisonRules()
    return rules, row.updated_at if row else None


def update_rules(db, project_id, rules):
    project_by_id(db, project_id)
    row = db.get(ProjectComparisonSettings, project_id)
    if not row:
        row = ProjectComparisonSettings(project_id=project_id, rules=rules.model_dump())
        db.add(row)
    else:
        row.rules = rules.model_dump()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.get(ProjectComparisonSettings, project_id)
        if not row:
            raise
        row.rules = rules.model_dump()
        db.commit()
    db.refresh(row)
    return {
        "project_id": project_id,
        "rules": rules,
        "rules_hash": rules.fingerprint(),
        "updated_at": row.updated_at,
    }


def load_result(db, result_id):
    result = db.scalar(
        select(ReplayResult)
        .where(ReplayResult.id == result_id)
        .options(
            joinedload(ReplayResult.original_recording),
            joinedload(ReplayResult.session),
        )
    )
    if not result:
        raise HTTPException(404, "Replay result not found.")
    validate_relationship(result)
    return result


def validate_relationship(result):
    if result.original_recording.project_id != result.session.project_id:
        raise HTTPException(
            409, "Original recording and replay session belong to different projects."
        )


def snapshot(record):
    return Snapshot(
        record.response_status,
        record.response_headers,
        record.response_body,
        record.response_body_kind,
        record.execution_error,
    )


def base_query(detail=False):
    query = select(Comparison).options(
        joinedload(Comparison.replay_result).joinedload(ReplayResult.session),
        joinedload(Comparison.replay_result).joinedload(
            ReplayResult.original_recording
        ),
    )
    return query.options(selectinload(Comparison.differences)) if detail else query


def get_comparison(db, comparison_id):
    row = db.scalar(base_query(True).where(Comparison.id == comparison_id))
    if not row:
        raise HTTPException(404, "Comparison not found.")
    validate_relationship(row.replay_result)
    return row


def existing(db, result_id, rules):
    return db.scalar(
        base_query(True).where(
            Comparison.replay_result_id == result_id,
            Comparison.algorithm_version == ALGORITHM_VERSION,
            Comparison.rules_hash == rules.fingerprint(),
        )
    )


def calculate(db, result, rules, cached=None):
    validate_relationship(result)
    if result.outcome in {"pending", "running"}:
        raise HTTPException(
            409, "Wait until this replay result is finalized before comparing."
        )
    if cached:
        return cached
    output = compare_snapshots(
        snapshot(result.original_recording), snapshot(result), rules
    )
    row = Comparison(
        replay_result_id=result.id,
        replay_result=result,
        comparison_status=output.comparison_status,
        original_status_code=result.original_recording.response_status,
        replay_status_code=result.response_status,
        total_differences=len(output.differences),
        counts=output.counts,
        effective_rules=rules.model_dump(),
        rules_hash=rules.fingerprint(),
        algorithm_version=ALGORITHM_VERSION,
        notes=output.notes,
        differences=[Difference(**item) for item in output.differences],
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Unique key makes simultaneous requests idempotent too.
        saved = existing(db, result.id, rules)
        if saved:
            return saved
        raise
    return row


def compare_result(db, result_id, requested_rules=None):
    result = load_result(db, result_id)
    current, _ = rules_for_project(db, result.session.project_id)
    rules = requested_rules or current
    row = calculate(db, result, rules, existing(db, result_id, rules))
    return view(row, current, detail=True)


def latest_for_result(db, result_id):
    result = load_result(db, result_id)
    rules, _ = rules_for_project(db, result.session.project_id)
    row = db.scalar(
        base_query(True)
        .where(Comparison.replay_result_id == result_id)
        .order_by(
            case(
                (
                    (Comparison.rules_hash == rules.fingerprint())
                    & (Comparison.algorithm_version == ALGORITHM_VERSION),
                    0,
                ),
                else_=1,
            ),
            Comparison.compared_at.desc(),
            Comparison.id,
        )
    )
    if not row:
        raise HTTPException(
            404, "No comparison yet. Compare this saved replay result first."
        )
    return view(row, rules, detail=True)


def view(row, current, detail=False):
    r = row.replay_result
    validate_relationship(r)
    keys = (
        "id",
        "replay_result_id",
        "comparison_status",
        "original_status_code",
        "replay_status_code",
        "total_differences",
        "counts",
        "effective_rules",
        "rules_hash",
        "algorithm_version",
        "compared_at",
        "notes",
    )
    data = {k: getattr(row, k) for k in keys}
    data.update(
        project_id=r.session.project_id,
        replay_session_id=r.replay_session_id,
        session_name=r.session.name,
        recording_name=r.original_recording.name,
        request_method=r.request_method,
        endpoint_path=r.endpoint_path,
        is_current=row.rules_hash == current.fingerprint()
        and row.algorithm_version == ALGORITHM_VERSION,
    )
    if detail:
        data["differences"] = row.differences
    return data


def session_comparisons(db, session_id, run=False, requested_rules=None):
    session = session_by_id(db, session_id)
    current, _ = rules_for_project(db, session.project_id)
    rules = requested_rules or current
    # One eager query for all sources; one for all prior comparisons.
    results = db.scalars(
        select(ReplayResult)
        .where(ReplayResult.replay_session_id == session_id)
        .order_by(ReplayResult.ordinal)
        .options(
            joinedload(ReplayResult.original_recording),
            joinedload(ReplayResult.session),
        )
    ).all()
    for result in results:
        validate_relationship(result)
    previous = db.scalars(
        base_query()
        .join(ReplayResult)
        .where(ReplayResult.replay_session_id == session_id)
        .order_by(Comparison.compared_at.desc(), Comparison.id)
    ).all()
    items = []
    for result in results:
        candidates = [c for c in previous if c.replay_result_id == result.id]
        match = next(
            (
                c
                for c in candidates
                if c.rules_hash == rules.fingerprint()
                and c.algorithm_version == ALGORITHM_VERSION
            ),
            None,
        )
        if run and result.outcome not in {"pending", "running"}:
            row = calculate(db, result, rules, match)
        else:
            row = match or (candidates[0] if candidates else None)
        if row:
            items.append(view(row, current))
    totals = dict.fromkeys(
        (
            "compared",
            "identical",
            "different",
            "incomparable",
            "differences",
            *CHANGE_TYPES,
        ),
        0,
    )
    for item in items:
        totals["compared"] += 1
        state = item["comparison_status"]
        totals[state if state in {"identical", "different"} else "incomparable"] += 1
        totals["differences"] += item["total_differences"]
        for kind, count in item["counts"].items():
            totals[kind] += count
    return {
        "session_id": session_id,
        "project_id": session.project_id,
        "session_name": session.name,
        "total_requests": session.total_requests,
        "pending_requests": sum(r.outcome in {"pending", "running"} for r in results),
        "items": items,
        "totals": totals,
    }


def history(db, project_id, limit, offset):
    rules, _ = rules_for_project(db, project_id)
    where = ReplaySession.project_id == project_id
    total = db.scalar(
        select(func.count(Comparison.id))
        .join(ReplayResult)
        .join(ReplaySession)
        .where(where)
    )
    rows = db.scalars(
        base_query()
        .join(ReplayResult)
        .join(ReplaySession)
        .where(where)
        .order_by(Comparison.compared_at.desc(), Comparison.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [view(row, rules) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def full_values(db, comparison_id, difference_id):
    row = get_comparison(db, comparison_id)
    difference = next((d for d in row.differences if d.id == difference_id), None)
    if not difference:
        raise HTTPException(404, "Difference not found in this comparison.")
    result = row.replay_result
    snapshots = [
        safe_snapshot(snapshot(result.original_recording)),
        safe_snapshot(snapshot(result)),
    ]
    values = []
    for source, present in zip(
        snapshots, [difference.old_present, difference.new_present]
    ):
        if not present:
            value = None
        elif difference.scope == "status":
            value = source.status
        elif difference.scope == "headers":
            value = resolve(source.headers, difference.path)
        else:
            value = resolve(source.body, difference.path)
        if value is MISSING:
            raise HTTPException(
                409, "Saved source no longer matches this immutable comparison."
            )
        values.append(value)
    return {
        "old_present": difference.old_present,
        "new_present": difference.new_present,
        "old_value": values[0],
        "new_value": values[1],
    }

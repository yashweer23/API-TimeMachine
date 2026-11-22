"""Immutable analyses keyed by comparison, effective policy and engine version."""

from urllib.parse import urlsplit, urlunsplit
from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.core.redaction import Redactor
from app.models.comparison import Comparison
from app.models.entities import Recording
from app.models.replay import ReplayResult, ReplaySession
from app.models.compatibility import (
    CompatibilityAnalysis,
    CompatibilityFinding,
    CompatibilityRun,
    CompatibilityRunItem,
    ProjectCompatibilityPolicies,
)
from app.schemas.compatibility import PolicyBundle, fingerprint
from app.schemas.comparison import ComparisonRules, DifferenceOut
from app.services import comparison_service as comparisons
from app.services.comparison_engine import ALGORITHM_VERSION
from app.services.compatibility_engine import (
    ENGINE_VERSION,
    CLASSES,
    assess,
    counts_for,
    verdict_for,
)
from app.services.catalog import project_by_id
from app.services.replay_service import session_by_id


def policies_for(db, project_id):
    project_by_id(db, project_id)
    row = db.get(ProjectCompatibilityPolicies, project_id)
    bundle = PolicyBundle.model_validate(row.policies) if row else PolicyBundle()
    return dict(
        project_id=project_id,
        policies=bundle,
        policies_hash=fingerprint(bundle.model_dump()),
        updated_at=row.updated_at if row else None,
    )


def save_policies(db, project_id, bundle):
    # Serialize writers on the project row on PostgreSQL. SQLite serializes writes itself.
    project = project_by_id(db, project_id)
    db.refresh(project, with_for_update=True)
    row = db.get(ProjectCompatibilityPolicies, project_id)
    if row:
        row.policies = bundle.model_dump()
    else:
        db.add(
            ProjectCompatibilityPolicies(
                project_id=project_id, policies=bundle.model_dump()
            )
        )
    db.commit()
    return policies_for(db, project_id)


def endpoint_policy(bundle, method, path):
    return next(
        (p for p in bundle.endpoints if p.method == method and p.endpoint_path == path),
        None,
    )


def analysis_query():
    return select(CompatibilityAnalysis)


def validate_analysis_sources(db, rows):
    if not rows:
        return
    source_rows = db.execute(
        select(
            CompatibilityAnalysis.id,
            ReplaySession.project_id,
            ReplayResult.replay_session_id,
            Recording.project_id,
        )
        .select_from(CompatibilityAnalysis)
        .join(Comparison, Comparison.id == CompatibilityAnalysis.comparison_id)
        .join(ReplayResult, ReplayResult.id == Comparison.replay_result_id)
        .join(ReplaySession, ReplaySession.id == ReplayResult.replay_session_id)
        .join(Recording, Recording.id == ReplayResult.original_recording_id)
        .where(CompatibilityAnalysis.id.in_([r.id for r in rows]))
    ).all()
    sources = {r[0]: r[1:] for r in source_rows}
    for row in rows:
        if sources.get(row.id) != (
            row.project_id,
            row.replay_session_id,
            row.project_id,
        ):
            raise HTTPException(409, "Analysis source relationships are inconsistent.")


def get_analysis(db, analysis_id):
    row = db.scalar(analysis_query().where(CompatibilityAnalysis.id == analysis_id))
    if not row:
        raise HTTPException(404, "Compatibility analysis not found.")
    validate_analysis_sources(db, [row])
    return row


def analyze_comparison(db, comparison_id, bundle=None):
    source = comparisons.get_comparison(db, comparison_id)
    result = source.replay_result
    if result.session.status == "running" or result.outcome in ("pending", "running"):
        raise HTTPException(
            409, "Finish the replay session before analyzing immutable evidence."
        )
    bundle = bundle or policies_for(db, result.session.project_id)["policies"]
    policy = endpoint_policy(bundle, result.request_method, result.endpoint_path)
    policy_json = policy.model_dump() if policy else None
    policy_hash = fingerprint(policy_json)
    query = analysis_query().where(
        CompatibilityAnalysis.comparison_id == comparison_id,
        CompatibilityAnalysis.engine_version == ENGINE_VERSION,
        CompatibilityAnalysis.policy_hash == policy_hash,
    )
    previous = db.scalar(query)
    if previous:
        return previous
    findings = assess(
        comparisons.snapshot(result.original_recording),
        comparisons.snapshot(result),
        [DifferenceOut.model_validate(d).model_dump() for d in source.differences],
        source.comparison_status,
        ComparisonRules.model_validate(source.effective_rules),
        policy,
    )
    counts = counts_for(findings)
    row = CompatibilityAnalysis(
        comparison_id=source.id,
        project_id=result.session.project_id,
        replay_session_id=result.replay_session_id,
        request_method=result.request_method,
        endpoint_path=result.endpoint_path,
        engine_version=ENGINE_VERSION,
        policy_hash=policy_hash,
        effective_policy=policy_json,
        effective_comparison_rules=source.effective_rules,
        comparison_algorithm_version=source.algorithm_version,
        verdict=verdict_for(counts),
        counts=counts,
        findings=[CompatibilityFinding(**f) for f in findings],
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(query)
        if previous:
            return previous
        raise
    return row


def analysis_view(db, row, bundle=None, rules=None):
    bundle = bundle or policies_for(db, row.project_id)["policies"]
    rules = rules or comparisons.rules_for_project(db, row.project_id)[0]
    current_policy = endpoint_policy(bundle, row.request_method, row.endpoint_path)
    keys = (
        "id",
        "project_id",
        "replay_session_id",
        "comparison_id",
        "request_method",
        "endpoint_path",
        "verdict",
        "counts",
        "effective_policy",
        "policy_hash",
        "effective_comparison_rules",
        "comparison_algorithm_version",
        "engine_version",
        "analyzed_at",
    )
    return {
        **{k: getattr(row, k) for k in keys},
        "is_current": row.engine_version == ENGINE_VERSION
        and row.policy_hash
        == fingerprint(current_policy.model_dump() if current_policy else None)
        and row.comparison_algorithm_version == ALGORITHM_VERSION
        and row.effective_comparison_rules == rules.model_dump(),
    }


def latest_analysis(db, comparison_id):
    source = comparisons.get_comparison(db, comparison_id)
    bundle = policies_for(db, source.replay_result.session.project_id)["policies"]
    policy = endpoint_policy(
        bundle, source.replay_result.request_method, source.replay_result.endpoint_path
    )
    row = db.scalar(
        analysis_query()
        .where(CompatibilityAnalysis.comparison_id == comparison_id)
        .order_by(
            case(
                (
                    (
                        CompatibilityAnalysis.policy_hash
                        == fingerprint(policy.model_dump() if policy else None)
                    )
                    & (CompatibilityAnalysis.engine_version == ENGINE_VERSION),
                    0,
                ),
                else_=1,
            ),
            CompatibilityAnalysis.analyzed_at.desc(),
            CompatibilityAnalysis.id,
        )
    )
    if not row:
        raise HTTPException(
            404, "No compatibility analysis yet. Analyze this comparison first."
        )
    return analysis_view(db, row, bundle)


def safe_base(value):
    parts = urlsplit(value)
    return urlunsplit(
        (parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", "")
    )


def analyze_session(db, session_id):
    session = session_by_id(db, session_id)
    if session.status == "running":
        raise HTTPException(
            409, "Finish the replay session before compatibility analysis."
        )
    bundle = policies_for(db, session.project_id)["policies"]
    selected = comparisons.session_comparisons(db, session_id)["items"]
    rows = [analyze_comparison(db, c["id"], bundle) for c in selected]
    result_ids = {c["replay_result_id"] for c in selected}
    missing = [str(r.id) for r in session.results if r.id not in result_ids]
    key = fingerprint({"analyses": [str(r.id) for r in rows], "missing": missing})
    query = select(CompatibilityRun).where(
        CompatibilityRun.replay_session_id == session.id,
        CompatibilityRun.engine_version == ENGINE_VERSION,
        CompatibilityRun.fingerprint == key,
    )
    previous = db.scalar(query)
    if previous:
        return previous
    summary = {
        k: sum(a.counts.get(k, 0) for a in rows)
        for k in (*CLASSES, "high_critical", "findings")
    }
    summary.update(
        replayed=sum(
            r.outcome not in ("pending", "running", "skipped") for r in session.results
        ),
        total_requests=session.total_requests,
        compared=len(rows),
        identical=sum(c["comparison_status"] == "identical" for c in selected),
        changed=sum(c["total_differences"] > 0 for c in selected),
        incomplete_comparisons=sum(
            c["comparison_status"] in ("partial", "limited", "unavailable")
            for c in selected
        ),
        missing_comparisons=len(missing),
        transport_failures=sum(r.outcome == "transport_error" for r in session.results),
        execution_failures=sum(r.outcome != "http_response" for r in session.results),
    )
    project = project_by_id(db, session.project_id)
    metadata = Redactor().clean(
        dict(
            project_name=project.name,
            session_name=session.name,
            source_base_urls=sorted(
                {safe_base(r.original_recording.base_url) for r in session.results}
            ),
            target_base_url=safe_base(session.target_base_url),
            session_status=session.status,
        )
    )
    row = CompatibilityRun(
        project_id=session.project_id,
        replay_session_id=session.id,
        engine_version=ENGINE_VERSION,
        fingerprint=key,
        verdict=verdict_for(
            summary,
            bool(missing) or not rows or len(session.results) != session.total_requests,
        ),
        summary=summary,
        metadata_snapshot=metadata,
        missing_result_ids=missing,
        items=[CompatibilityRunItem(ordinal=i, analysis=a) for i, a in enumerate(rows)],
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(query)
        if previous:
            return previous
        raise
    return row


def run_query():
    return select(CompatibilityRun).options(
        selectinload(CompatibilityRun.items).joinedload(CompatibilityRunItem.analysis)
    )


def get_run(db, run_id):
    row = db.scalar(run_query().where(CompatibilityRun.id == run_id))
    if not row:
        raise HTTPException(404, "Compatibility run not found.")
    session = session_by_id(db, row.replay_session_id)
    if session.project_id != row.project_id or any(
        i.analysis.project_id != row.project_id
        or i.analysis.replay_session_id != row.replay_session_id
        for i in row.items
    ):
        raise HTTPException(
            409, "Compatibility run source relationships are inconsistent."
        )
    validate_analysis_sources(db, [item.analysis for item in row.items])
    return row


def run_view(db, row, bundle=None, rules=None):
    bundle = (
        bundle if bundle is not None else policies_for(db, row.project_id)["policies"]
    )
    rules = (
        rules
        if rules is not None
        else comparisons.rules_for_project(db, row.project_id)[0]
    )
    analyses = [analysis_view(db, i.analysis, bundle, rules) for i in row.items]
    keys = (
        "id",
        "project_id",
        "replay_session_id",
        "engine_version",
        "verdict",
        "summary",
        "metadata_snapshot",
        "missing_result_ids",
        "analyzed_at",
    )
    return {
        **{k: getattr(row, k) for k in keys},
        "analyses": analyses,
        "is_current": bool(analyses)
        and not row.missing_result_ids
        and all(a["is_current"] for a in analyses),
    }


def latest_run(db, session_id):
    session = session_by_id(db, session_id)
    bundle = policies_for(db, session.project_id)["policies"]
    selected = comparisons.session_comparisons(db, session_id)["items"]
    analysis_ids = []
    for item in selected:
        policy = endpoint_policy(bundle, item["request_method"], item["endpoint_path"])
        analysis = db.scalar(
            select(CompatibilityAnalysis).where(
                CompatibilityAnalysis.comparison_id == item["id"],
                CompatibilityAnalysis.engine_version == ENGINE_VERSION,
                CompatibilityAnalysis.policy_hash
                == fingerprint(policy.model_dump() if policy else None),
            )
        )
        if analysis is None:
            break
        analysis_ids.append(str(analysis.id))
    row = None
    if len(analysis_ids) == len(selected):
        compared = {c["replay_result_id"] for c in selected}
        missing = [str(r.id) for r in session.results if r.id not in compared]
        key = fingerprint({"analyses": analysis_ids, "missing": missing})
        row = db.scalar(
            run_query().where(
                CompatibilityRun.replay_session_id == session_id,
                CompatibilityRun.engine_version == ENGINE_VERSION,
                CompatibilityRun.fingerprint == key,
            )
        )
    if row is None:
        row = db.scalar(
            run_query()
            .where(CompatibilityRun.replay_session_id == session_id)
            .order_by(CompatibilityRun.analyzed_at.desc(), CompatibilityRun.id)
        )
    if not row:
        raise HTTPException(
            404,
            "No compatibility run yet. Compare saved responses, then analyze this session.",
        )
    return run_view(db, get_run(db, row.id))


def history(db, project_id, limit, offset):
    bundle = policies_for(db, project_id)["policies"]
    rules = comparisons.rules_for_project(db, project_id)[0]
    query = run_query().where(CompatibilityRun.project_id == project_id)
    total = db.scalar(
        select(func.count())
        .select_from(CompatibilityRun)
        .where(CompatibilityRun.project_id == project_id)
    )
    rows = db.scalars(
        query.order_by(CompatibilityRun.analyzed_at.desc(), CompatibilityRun.id)
        .limit(limit)
        .offset(offset)
    ).all()
    validate_analysis_sources(db, [item.analysis for row in rows for item in row.items])
    return dict(
        items=[run_view(db, r, bundle, rules) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def findings_page(
    db,
    analysis_ids,
    limit,
    offset,
    classification=None,
    severity=None,
    method=None,
    endpoint=None,
    search=None,
):
    query = (
        select(CompatibilityFinding, CompatibilityAnalysis)
        .join(CompatibilityAnalysis)
        .where(CompatibilityFinding.analysis_id.in_(analysis_ids))
    )
    if classification:
        query = query.where(CompatibilityFinding.classification == classification)
    if severity:
        query = query.where(
            CompatibilityFinding.severity.is_(None)
            if severity == "unrated"
            else CompatibilityFinding.severity == severity
        )
    if method:
        query = query.where(CompatibilityAnalysis.request_method == method)
    if endpoint:
        query = query.where(
            CompatibilityAnalysis.endpoint_path.contains(endpoint, autoescape=True)
        )
    if search:
        query = query.where(
            CompatibilityFinding.path.contains(search, autoescape=True)
            | CompatibilityFinding.title.contains(search, autoescape=True)
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    pairs = db.execute(
        query.order_by(
            CompatibilityAnalysis.request_method,
            CompatibilityAnalysis.endpoint_path,
            CompatibilityAnalysis.id,
            CompatibilityFinding.ordinal,
        )
        .offset(offset)
        .limit(limit)
    ).all()
    keys = (
        "id",
        "analysis_id",
        "difference_id",
        "ordinal",
        "scope",
        "path",
        "change_type",
        "classification",
        "severity",
        "confidence",
        "title",
        "explanation",
        "recommended_action",
        "rule_id",
        "evidence",
    )
    items = [
        {
            **{k: getattr(f, k) for k in keys},
            "comparison_id": a.comparison_id,
            "request_method": a.request_method,
            "endpoint_path": a.endpoint_path,
        }
        for f, a in pairs
    ]
    return dict(items=items, total=total, limit=limit, offset=offset)

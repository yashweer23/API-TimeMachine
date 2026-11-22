import os
from datetime import datetime, timezone
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, null, select
from app.core.config import get_settings


def test_upgrade_preserves_phase1_rows_and_downgrade(tmp_path, monkeypatch):
    url = os.getenv("TEST_MIGRATION_DATABASE_URL") or "sqlite:///" + str(
        tmp_path / "migration.db"
    )
    engine = create_engine(url)
    assert not inspect(engine).get_table_names(), (
        "Use a separate EMPTY database for migration tests."
    )
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    try:
        command.upgrade(cfg, "0001_initial")
        meta = MetaData()
        projects = Table("projects", meta, autoload_with=engine)
        recordings = Table("recordings", meta, autoload_with=engine)

        def new_id():
            return uuid4().hex if engine.dialect.name == "sqlite" else uuid4()

        project_id = new_id()
        ids = [new_id(), new_id()]
        now = datetime.now(timezone.utc)
        with engine.begin() as c:
            c.execute(
                projects.insert().values(
                    id=project_id,
                    name="Legacy project",
                    base_url="https://api.example.test",
                    created_at=now,
                    updated_at=now,
                )
            )
            for i, record_id in enumerate(ids):
                c.execute(
                    recordings.insert().values(
                        id=record_id,
                        project_id=project_id,
                        name="Legacy " + str(i),
                        method="GET",
                        base_url="https://api.example.test",
                        endpoint_path="/users",
                        query_parameters={},
                        request_headers={},
                        request_body=null() if i == 0 else {"preserve": True},
                        response_status=200,
                        response_headers={},
                        response_body={"legacy": [1, None, True]},
                        response_body_kind="json",
                        duration_ms=1.2,
                        captured_at=now,
                        is_baseline=True,
                    )
                )
            before = [
                dict(r)
                for r in c.execute(
                    select(recordings).order_by(recordings.c.name)
                ).mappings()
            ]
        command.upgrade(cfg, "0002_replay_sessions")
        session_table = Table("replay_sessions", MetaData(), autoload_with=engine)
        result_table = Table("replay_results", MetaData(), autoload_with=engine)
        session_id, result_id = new_id(), new_id()
        with engine.begin() as c:
            c.execute(
                session_table.insert().values(
                    id=session_id,
                    project_id=project_id,
                    name="Preserved replay",
                    target_base_url="https://api.example.test/v2",
                    status="completed",
                    total_requests=1,
                    completed_requests=1,
                    failed_requests=0,
                    error_requests=0,
                    http_responses=1,
                    skipped_requests=0,
                    started_at=now,
                    completed_at=now,
                    duration_ms=1.2,
                )
            )
            c.execute(
                result_table.insert().values(
                    id=result_id,
                    replay_session_id=session_id,
                    original_recording_id=ids[0],
                    ordinal=0,
                    request_method="GET",
                    endpoint_path="/users",
                    replay_url="https://api.example.test/v2/users",
                    request_metadata={"body_present": False},
                    outcome="http_response",
                    response_status=201,
                    response_headers={"x-repeat": ["a", "b"]},
                    response_body={"keep": [1, None]},
                    response_body_kind="json",
                    content_type="application/json",
                    duration_ms=1.2,
                    executed_at=now,
                )
            )
            replay_before = [
                dict(r) for r in c.execute(select(result_table)).mappings()
            ]
            session_before = [
                dict(r) for r in c.execute(select(session_table)).mappings()
            ]
        command.upgrade(cfg, "0003_comparisons")
        comparison_table = Table("comparisons", MetaData(), autoload_with=engine)
        difference_table = Table(
            "comparison_differences", MetaData(), autoload_with=engine
        )
        settings_table = Table(
            "project_comparison_settings", MetaData(), autoload_with=engine
        )
        comparison_id = new_id()
        with engine.begin() as c:
            c.execute(
                comparison_table.insert().values(
                    id=comparison_id,
                    replay_result_id=result_id,
                    comparison_status="different",
                    original_status_code=200,
                    replay_status_code=201,
                    total_differences=1,
                    counts={"status_changed": 1},
                    effective_rules={
                        "ignored_headers": [],
                        "ignored_json_paths": [],
                        "unordered_array_paths": [],
                    },
                    rules_hash="a" * 64,
                    algorithm_version="pointer-v1",
                    compared_at=now,
                    notes=[],
                )
            )
            c.execute(
                difference_table.insert().values(
                    id=new_id(),
                    comparison_id=comparison_id,
                    ordinal=0,
                    scope="status",
                    path="/status",
                    change_type="status_changed",
                    old_type="number",
                    new_type="number",
                    old_present=True,
                    new_present=True,
                    old_value=200,
                    new_value=201,
                    old_preview="200",
                    new_preview="201",
                    old_value_truncated=False,
                    new_value_truncated=False,
                )
            )
            c.execute(
                settings_table.insert().values(
                    project_id=project_id,
                    rules={
                        "ignored_headers": ["date"],
                        "ignored_json_paths": [],
                        "unordered_array_paths": [],
                    },
                    updated_at=now,
                )
            )
            phase3_before = {
                table.name: [dict(r) for r in c.execute(select(table)).mappings()]
                for table in (comparison_table, difference_table, settings_table)
            }
        command.upgrade(cfg, "head")
        command.check(cfg)
        command.downgrade(cfg, "0003_comparisons")
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            for table in (comparison_table, difference_table, settings_table):
                assert [
                    dict(r) for r in c.execute(select(table)).mappings()
                ] == phase3_before[table.name]
        with engine.connect() as c:
            assert [
                dict(r) for r in c.execute(select(result_table)).mappings()
            ] == replay_before
            assert [
                dict(r) for r in c.execute(select(session_table)).mappings()
            ] == session_before
        command.downgrade(cfg, "0002_replay_sessions")
        with engine.connect() as c:
            assert [
                dict(r) for r in c.execute(select(result_table)).mappings()
            ] == replay_before
        command.upgrade(cfg, "head")
        table = Table("recordings", MetaData(), autoload_with=engine)
        with engine.connect() as c:
            after = [
                dict(r)
                for r in c.execute(select(table).order_by(table.c.name)).mappings()
            ]
        assert after[0].pop("request_body_present") is None
        assert after[1].pop("request_body_present") is True
        assert after == before
        command.check(cfg)
        command.downgrade(cfg, "0001_initial")
        with engine.connect() as c:
            assert [
                dict(r)
                for r in c.execute(
                    select(recordings).order_by(recordings.c.name)
                ).mappings()
            ] == before
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
    finally:
        engine.dispose()
        get_settings.cache_clear()

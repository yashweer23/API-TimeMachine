# Phase 2 — Replay engine and execution history

Phase 2 adds explicit single and batch replay, persistent execution history, and a two-panel response inspector. Phase 1 project management, recording, metadata editing, baselines, and target protections remain available. Responses are shown for manual inspection; automatic comparison belongs to Phase 3.

## Upgrade an existing Phase 1 project

1. Stop the old stack with `docker compose down` from its original folder. Do **not** add `-v` or delete the database volume.
2. Back up important data. Copy the Phase 2 source into your existing project folder, keeping your `.env`, database password, custom settings, and named volume. The Compose project name remains `api-timemachine`.
3. If you have a root `.env`, append `http://sample-api-v2:8001` to both `ALLOWED_TARGET_ORIGINS` and `DEV_PRIVATE_ORIGINS`. Keep previous approved origins. Old `.env` values override new Compose defaults.
4. Run `docker compose up --build`. Backend startup applies `alembic upgrade head` automatically.
5. Open Recordings to check existing captures, then open Replay.

Default lists now contain:

```dotenv
ALLOWED_TARGET_ORIGINS=http://sample-api:8001,http://sample-api-v2:8001
DEV_PRIVATE_ORIGINS=http://sample-api:8001,http://sample-api-v2:8001
```

For native development, use `http://127.0.0.1:8001,http://127.0.0.1:8004` in both lists in `backend/.env`, retain the loopback CIDR exception, and run `python -m alembic upgrade head` from `backend` before starting it.

### Migration

`0002_replay_sessions` follows `0001_initial`. It creates `replay_sessions` and `replay_results`, with UUID primary keys, project/original-recording foreign keys, ordered result relationships, uniqueness constraints, status/count checks, and lookup indexes. Request/response metadata uses PostgreSQL JSONB.

It also adds nullable `recordings.request_body_present`. Existing non-null bodies are marked present; legacy null bodies remain unknown because Phase 1 did not distinguish an absent body from JSON `null`. No original request or response content is rewritten. For those legacy recordings, choose **No body** or **Replace with JSON** before replay; enter `null` if the original deliberately sent JSON null.

Downgrading to `0001_initial` removes replay history and the presence column while preserving Phase 1 recordings. Do not downgrade merely to restart the app.

## Five-minute demo

1. Open http://localhost:5175 and choose **Start with the sample API** or select your existing sample project. Its recording target is `http://sample-api:8001`.
2. Record `GET /users/1` and `GET /products` in Workspace.
3. Record `POST /echo` with `{"message":"hello from v1"}`. Avoid sensitive keys for this first demonstration so no replacement is needed.
4. Open **Replay**, select those recordings in the desired execution order, and choose `http://sample-api-v2:8001` as the target.
5. Name the run, review the requests, click **Run replay**, and confirm the POST side-effect warning.
6. Inspect each result using the **Body**, **Headers**, and **Request** tabs. Each snapshot has a copy button.
7. Open **Replay history**, refresh, and reopen the session. Restart the stack without removing its volume and reopen it again.

| Endpoint | v1 | v2 |
| --- | --- | --- |
| `GET /users/1` | `name`, integer `id`, `role`, `active` | `full_name`, string `id`, added `account_status`; `role`/`active` absent |
| `GET /products` | Numeric `price`, `in_stock` | String `price`, `availability`; `in_stock` absent |
| `POST /echo` | HTTP 200 | HTTP 201 |

For one recording, open its detail page and click **Replay this recording**. It is preselected without being sent. Each explicit run creates a new session and leaves originals unchanged.

## API endpoints

| Method | Route | Behavior |
| --- | --- | --- |
| POST | `/api/projects/{project_id}/replay-sessions` | Execute ordered batch; return finalized session with result summaries (`201`) |
| GET | `/api/projects/{project_id}/replay-sessions` | Paged history: `limit` 1–100 (default 20), `offset` default 0 |
| GET | `/api/replay-sessions/{session_id}` | Session and ordered result summaries |
| GET | `/api/replay-sessions/{session_id}/results` | Ordered result summaries |
| GET | `/api/replay-results/{result_id}` | Full sanitized replay plus referenced original recording |
| POST | `/api/recordings/{recording_id}/replay` | Single-recording convenience endpoint using the same service |
| GET | `/api/replay-config` | Approved origins, limits, execution mode |

Use actual recording UUIDs returned by the send/list endpoints:

```json
{
  "name": "API v2 regression run",
  "target_base_url": "http://sample-api-v2:8001",
  "recording_ids": ["<recording UUID>", "<another recording UUID>"],
  "confirm_side_effects": true
}
```

`201` means the execution was saved, including executions with failures. Inspect session `status`, result `outcome`, `response_status`, and `execution_error`. HTTP 400/404/500 remain real HTTP responses. A pre-response failure has null `response_status`; an incomplete capture can retain an actual status with an explicit error.

Malformed input returns `422`; missing resources return `404`; cross-project selections/prohibited origins return `403`; missing mutation confirmation returns `409`; full replay capacity returns `429`; database unavailability returns `503`. DNS/address policy failures discovered during execution are saved as blocked results.

## Temporary credentials and supported overrides

Replace or explicitly remove **every** `[REDACTED]` placeholder before running. Temporary headers apply to all selected requests and override stored/per-recording headers case-insensitively. Transport-controlled headers remain prohibited.

Example single-recording request:

```json
{
  "name": "Authenticated v2 check",
  "target_base_url": "http://sample-api-v2:8001",
  "confirm_side_effects": true,
  "temporary_headers": {"Authorization": "Bearer <temporary token>"},
  "override": {
    "headers": {"Cookie": null},
    "query_parameters": {"tag": ["one", "two"]},
    "body": {"message": "replacement body"}
  }
}
```

For a batch, use `overrides: {"<recording UUID>": {...}}` instead of `override`. Overrides merge/remove headers, replace the entire query map, replace the JSON body, or set `omit_body: true`. Empty query objects clear queries. Omitting `body` preserves it; `body: null` sends JSON null. `omit_body` and `body` cannot be combined. Method and endpoint cannot be overridden.

Temporary values remain in execution memory and are excluded from application logs and stored snapshots. **All** explicitly supplied override values, including nonstandard credential names, are treated as private and scrubbed from recognized echoes. Coincidentally matching response values may also be masked. The UI clears temporary headers and overrides when execution starts. Only the selected project ID is saved in local storage. Transformed/encoded secrets can defeat exact-value redaction; this is not a universal PII detector.

## Execution model and outcomes

- Execution is synchronous and sequential per session. The POST stays open until completion; there is no queue, scheduler, automatic resume, or retry.
- Defaults: **10 recordings**, **120 seconds execution budget**, **2 concurrent sessions**. Configurable maxima are 25, 300 seconds, and 8. Per-request deadlines and response limits still apply.
- Remaining session time limits each outbound call. Database persistence and validation can add overhead beyond the budget; it is not an absolute HTTP response deadline.
- Pending results are saved before execution and each settled result is committed. Leaving the page does not prove cancellation; check history before repeating writes.
- Use **one backend process**. Startup marks abandoned sessions interrupted, distinguishes previously running requests from pending/not-executed ones, and never retries them. This recovery does not coordinate workers or replicas.
- Database failure after an outbound call can prevent full persistence even when the target processed it. Inspect the target before retrying mutations.

| Field | Meaning |
| --- | --- |
| `completed_requests` | Finalized results, including failures/skipped requests; not success count |
| `http_responses` | Results with a real status, including incomplete captures |
| `failed_requests` | Transport errors only: timeouts/connection failures |
| `error_requests` | All execution issues, including skipped/interrupted/policy/capture errors |
| `skipped_requests` | Selected requests never started |
| `duration_ms` | Session or individual request duration |

Session states: `running`, `completed`, `completed_with_errors`, `timed_out`, `interrupted`. Result outcomes: `pending`, `running`, `http_response`, `transport_error`, `capture_error`, `blocked`, `skipped`, `interrupted`. A complete HTTP 500 alone is not a session execution failure.

## Important files

| File | Responsibility |
| --- | --- |
| `backend/app/services/replay_service.py` | Reconstruction, sequential execution, counts, persistence, recovery |
| `backend/app/services/recorder.py` | Shared secure HTTP capture for recording/replay |
| `backend/app/core/redaction.py` | Temporary-value and echo sanitization |
| `backend/app/models/replay.py` | Session/result tables and relationships |
| `backend/app/schemas/replay.py` | Replay input/output contracts |
| `backend/app/api/replay_routes.py` | Replay REST routes |
| `backend/alembic/versions/0002_replay_sessions.py` | Data-preserving upgrade |
| `frontend/src/pages/ReplayWorkspace.tsx` | Selection, config, overrides, confirmation |
| `frontend/src/pages/ReplayHistory.tsx` | Paginated persistent history |
| `frontend/src/pages/ReplaySessionDetails.tsx` | Results and read-only progress polling |
| `frontend/src/components/replay/ResponseViewer.tsx` | Paired body/header/request views and copy |
| `frontend/src/components/replay/ReplaySummary.tsx` | Status, timestamps, outcome counters |
| `frontend/src/services/replayPreparation.ts` | Client-side reconstruction validation |
| `frontend/src/services/replayApi.ts`, `frontend/src/types/replay.ts` | Typed client and contracts |
| `sample-api/main.py`, `compose.yaml` | Independent v1/v2 fixtures and five services |
| `backend/tests/test_replay.py`, `backend/tests/test_migrations.py` | Replay/security/failure/migration tests |
| `frontend/src/tests/replay.test.tsx`, `frontend/e2e/replay.spec.ts` | DOM coverage and local browser flow |
| `scripts/replay_smoke_test.py` | Live v1→v2 integration demonstration |

See [the Phase 2 verification report](VERIFICATION_PHASE2.md) for executed checks and remaining Docker/browser validation, and [PHASE3.md](PHASE3.md) for the implemented comparison engine. Breaking-change classification belongs to Phase 4.

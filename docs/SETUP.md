# Setup and API reference

Docker quick start and local URLs are in the [README](../README.md).

## Native development

Use Python 3.12+ and Node.js 22.12+ (Node 24 also works). Start only the database with Compose:

```sh
docker compose up -d db
```

From the project root, create the Python environment:

```sh
python -m venv .venv
```

**PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

**bash:**

```sh
.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
```

Use four VS Code terminals. The commands below use PowerShell paths; on bash replace `..\.venv\Scripts\python.exe` with `../.venv/bin/python`.

**Terminal 1 — sample API v1**

```powershell
cd sample-api
$env:API_VERSION="v1"
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001 --no-access-log
```

**Terminal 2 — sample API v2**

```powershell
cd sample-api
$env:API_VERSION="v2"
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8004 --no-access-log
```

On bash, use `API_VERSION=v1 ../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001 --no-access-log` for v1 and the equivalent `API_VERSION=v2` / port `8004` command for v2.

**Terminal 3 — backend**

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload --no-access-log
```

**Terminal 4 — frontend**

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5175. The one-click sample project and Replay target now follow `SAMPLE_V1_BASE_URL` and `SAMPLE_V2_BASE_URL` from `backend/.env`. With the supplied native example they use `http://127.0.0.1:8001` and `http://127.0.0.1:8004`. Existing native configurations should add those two variables. Both targets must remain in `ALLOWED_TARGET_ORIGINS` and the explicit private-development allowlist.

The backend loads `.env` from its working directory. Root `.env` is for Compose; `backend/.env` is for native development. The Vite development proxy defaults to `http://127.0.0.1:8002`; set `API_PROXY_TARGET` if the native backend port changes.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_PORT` | `5175` | Frontend host port |
| `BACKEND_PORT` | `8002` | Backend host port |
| `POSTGRES_PORT` | `5434` | Database host port |
| `SAMPLE_API_PORT` | `8003` | Sample API v1 host port |
| `SAMPLE_API_V2_PORT` | `8004` | Sample API v2 host port |
| `POSTGRES_PASSWORD` | `local-development-only` | Disposable local database password; use URL-safe characters |
| `DATABASE_URL` | Composed internally / native example | SQLAlchemy PostgreSQL connection URI |
| `ALLOWED_TARGET_ORIGINS` | Both sample service origins | Exact permitted origins, comma-separated; no wildcards |
| `DEV_PRIVATE_ORIGINS` | Both sample service origins | Explicit private-target development exceptions |
| `DEV_PRIVATE_CIDRS` | RFC1918 ranges | Address ranges permitted for those development origins |
| `CORS_ORIGINS` | localhost/127.0.0.1 frontend | Browser origins allowed to write, including backend docs; Compose derives ports |
| `TRUSTED_HOSTS` | localhost,127.0.0.1,backend | Accepted incoming Host values in Compose |
| `REDACT_FIELDS` | empty | Additional sensitive JSON/query/header keys, comma-separated |
| `CONNECT_TIMEOUT_SECONDS` | `3` | DNS and connection limit |
| `READ_TIMEOUT_SECONDS` | `10` | Read/write/pool timeout |
| `TOTAL_TIMEOUT_SECONDS` | `20` | Whole operation deadline, including queue and body stream |
| `MAX_RESPONSE_BYTES` | `1048576` | Raw body capture limit (1 MiB) |
| `MAX_REQUEST_BYTES` | `262144` | Incoming JSON payload cap (256 KiB) |
| `SAMPLE_V1_BASE_URL` / `SAMPLE_V2_BASE_URL` | Matching Docker/native sample targets | Safe UI defaults; does not grant execution permission |
| `MAX_EXECUTIONS_PER_MINUTE` | `120` | Shared rolling 60-second admission budget for capture/replay per process |
| `MAX_CONCURRENT_REQUESTS` | `8` | In-flight outbound requests per backend process |
| `REPLAY_MAX_BATCH_SIZE` | `10` | Recordings per replay session (maximum 25) |
| `REPLAY_SESSION_TIMEOUT_SECONDS` | `120` | Session execution budget (maximum 300 seconds); persistence can add overhead |
| `REPLAY_MAX_CONCURRENT_SESSIONS` | `2` | Concurrent sessions (maximum 8); full capacity returns 429 |

To permit a public API, add its exact origin to `ALLOWED_TARGET_ORIGINS` and restart/recreate the backend. Private APIs additionally require their exact origin in `DEV_PRIVATE_ORIGINS` **and** an appropriate narrow CIDR. Do not add public APIs to the private exception list. Keep development exceptions as narrow as your environment allows.

Project base URLs may contain a path prefix: `https://api.example.com/v1` plus `/users` becomes `/v1/users`. Put query parameters in the query editor, not the path or base URL. Repeated query keys are supported; duplicate headers are rejected. Project target changes affect future captures; old recordings retain their original base URL.

## API contract

| Method | Endpoint | Result |
| --- | --- | --- |
| POST | `/api/projects` | Create an allowlisted project (`201`) |
| GET | `/api/projects` | List projects |
| GET | `/api/projects/{id}` | Project details |
| PATCH | `/api/projects/{id}` | Update name, description, or base URL |
| POST | `/api/projects/{id}/requests/send` | Execute once and persist a recording (`201`) |
| GET | `/api/projects/{id}/recordings` | Paged summaries; `limit`, `offset`, optional `baseline`, `search`, `method` |
| GET | `/api/recordings/{id}` | Full sanitized snapshot |
| PATCH | `/api/recordings/{id}` | Rename, change label, or toggle baseline |
| GET | `/api/config` | Allowed sample targets, execution rate, mode and release version only |
| POST | `/api/replay-sessions/{id}/assess` | Compare saved responses, then assess; returns exact compatibility run |
| GET | `/api/health` | Database connectivity and API health |

The send endpoint returns `201` when a recording is saved, including a recorded execution failure. Read `response_status` and `execution_error`, not the outer API status, to determine what happened at the target. A pre-response failure has a null `response_status`. A failure while reading a real response retains its actual status and marks the body omitted. Incomplete captures cannot be baselines. A complete `404`, for example, can be an intentional baseline.

Example send payload:

```json
{
  "method": "POST",
  "endpoint_path": "/echo",
  "headers": {"X-Client": "TimeMachine"},
  "query_parameters": {"tag": ["first", "second"]},
  "body": {"message": "hello"},
  "name": "Echo reference",
  "environment_label": "v1-local"
}
```

Omit `body` for no HTTP body; `"body": null` sends JSON `null`. The UI sends no body when its editor is blank. Use `null` in the editor to send JSON null.

Full response bodies and requests are not included in list summaries. Pagination keeps the explorer reasonably small. The full snapshot includes `response_body_kind` (`json`, `text`, `empty`, `omitted`) so a JSON string/null is not confused with text or an empty response.

All seven replay routes and override payloads are documented in the [Phase 2 API contract](PHASE2.md#api-endpoints) and generated OpenAPI at `/docs`.


## Existing installations

Keep the database volume and existing `.env`. Extract the release into a new source folder, copy your configuration, and run Compose with the same project name (`api-timemachine`). Do not use `down -v`. Phase 5 adds no migration; startup runs migrations through `0004_compatibility`. For an older Phase 1 installation, follow [the Phase 2 upgrade instructions](PHASE2.md#upgrade-an-existing-phase-1-project) to add the v2 target.

Compose defaults include both sample URLs and the execution-rate setting. Add explicit sample URLs to an existing native `backend/.env`. If a host port conflicts, change the root `.env` host-port setting; internal Docker target URLs stay the same. A changed PostgreSQL password must agree with the existing volume's database credentials.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Sample target blocked | Exact origin plus development origin and CIDR must permit the resolved address; restart the backend after changes. |
| Native sample button has no target | Set both `SAMPLE_*_BASE_URL` variables in `backend/.env`; launch the backend from `backend`. |
| Docker capture to localhost fails | Use `http://sample-api:8001` / `http://sample-api-v2:8001` as backend targets. Host ports are for browser access. |
| Browser write rejected | Add the exact frontend origin to CORS settings when changing native ports; Compose derives local CORS origins from its port variables. |
| `execution_rate_limited` | Wait for the rolling one-minute window; no request was sent. This limit is shared by captures and replay. |
| Write succeeded but persistence failed | Inspect the target before retrying; automatic retries are deliberately disabled. |
| Report too large | Use paginated finding endpoints or a smaller replay session; no partial download is presented as complete. |
| Backend has no database connection | Confirm PostgreSQL health, credentials and host port. `/api/health` checks the database. |

[README](../README.md) · [Demo](DEMO.md) · [Verification](VERIFICATION.md)

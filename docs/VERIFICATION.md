# Phase 5 verification report

> Later interface revision: [INTERFACE.md](INTERFACE.md) records the visual redesign, fresh build/UI checks and manual desktop-browser workflow. The report below describes the original Phase 5 release checks.

Verified **19 November 2026 (Asia/Calcutta)**. This report separates executed checks from implemented but unexecuted browser/container checks. Earlier evidence is archived in [VERIFICATION_PHASE4.md](VERIFICATION_PHASE4.md).

## Executed results

| Command / check | Actual result | Scope |
| --- | --- | --- |
| Backend: `python -m pytest -q` | **209 passed**, one upstream warning; 14.97 seconds | PostgreSQL 16.2 with isolated per-test schemas; separate empty PostgreSQL database for migration round trips. All 203 prior tests retained plus six release tests. |
| Frontend: `npm run build` | **Passed** | Strict TypeScript + Vite production build; 1,672 modules; JS 338.25 kB / 101.77 kB gzip; CSS 45.77 kB / 10.62 kB gzip. These are bundle sizes, not performance measurements. |
| Frontend: `npm test` | **27 passed** across five files | Vitest/jsdom, mocked backend; eight added release interactions, existing tests retained. |
| Frontend: `npm run test:e2e -- --list` | **6 tests discovered** across five files | Discovery/parser check only. No real browser pass. |
| `python -m ruff check backend/app backend/tests scripts sample-api` | **Passed** | Project-local E4/E7/E9/F syntax/core-Pyflakes scope, pinned Ruff 0.17.5; independent of inherited workspace lint configuration. |
| `python -m pytest -q -s tests/test_release.py::test_history_queries_do_not_scale_per_run` | **1 passed** | Final instrumentation: 8 SELECTs for two runs, 8 for ten runs, using SQLite service fixtures. |
| Focused compatibility API tests after lint-only HTML helper cleanup | **5 passed** | Reports, escaping/limits, policy/history, integrity and immutable source behavior; SQLite test fixtures. |
| `python -m alembic upgrade head` | **Passed** | Existing PostgreSQL application database; head `0004_compatibility`, no Phase 5 migration required. |
| `python -m alembic check` | **Passed** | No new upgrade operations detected. |
| `python scripts/smoke_test.py --target http://127.0.0.1:8001` | **Passed** | Real capture, POST body/types/redaction, baseline/list/rename persistence, genuine 404. |
| `python scripts/replay_smoke_test.py --backend http://127.0.0.1:5175 --v1 http://127.0.0.1:8001 --v2 http://127.0.0.1:8004` | **Passed** | Actual v1→v2 batch/single sessions, five intentional changes, unchanged originals, transient credential redaction, saved history. |
| `python scripts/comparison_smoke_test.py --backend http://127.0.0.1:5175 --v1 http://127.0.0.1:8001 --v2 http://127.0.0.1:8004` | **Passed** | Thirteen live fixtures, JSON/status/multivalue headers/text/empty responses, ignored timestamp, unordered arrays, deterministic reuse and immutable evidence. |
| `python scripts/compatibility_smoke_test.py --backend http://127.0.0.1:5175 --v1 http://127.0.0.1:8001 --v2 http://127.0.0.1:8004` | **Passed** | Ten live fixtures, real timeout distinct from HTTP 500, four explicit violations, policy precedence/reanalysis, historical JSON/HTML exports. |
| `python scripts/release_demo.py --backend http://127.0.0.1:5175 --report-dir <temporary-report-directory>` | **Passed** | Real project→GET baseline→replay→combined assessment→policy→history/download journey; 0 then 2 confirmed findings, source preservation and ID reuse. |
| Additional live HTTP | **Passed** | `/text`: 200; `/redirect`: 302, not followed; `/slow`: null status with timeout. |
| Backend restart | **Passed** | Historical compatibility details/report bytes, comparisons/differences and replay history survived process termination and restart. |
| OpenAPI inspection | **Passed** | 13 compatibility operations, including combined assessment; release version 1.0.0, health phase 5. |
| Compose static inspection | **Passed** | Unique YAML keys, five services, valid build contexts, health dependencies, loopback-only ports, named database volume, migration startup, sample defaults and frontend proxy. |

The live workflow ran independent sample v1/v2, backend and Vite processes against PostgreSQL, with requests routed through the frontend proxy for Phase 2–5 checks. This establishes actual HTTP/database integration. It does not establish browser rendering or Docker networking.

## Data preservation

Before the release workflow, migration/startup preserved 131 existing recordings, 25 replay sessions, 97 replay results, 80 comparisons, 94 differences, four comparison settings rows, 40 compatibility analyses, 48 findings, four runs, 40 run memberships and two policy rows. The end-to-end checks then created additional development data. Seeded migration round trips were also included in the backend suite.

## New correctness coverage

Backend additions cover the bounded history query count, summary-column projection/literal search/method filtering, combined assessment without outbound execution, shared capture/replay rate limiting and rolling-window recovery, safe runtime configuration, and source-project integrity on report/history reads. Existing suites continue to cover DNS/IP pinning, redirects, timeouts, 404/500, empty/null/invalid/oversized responses, nested JSON and arrays, invalid identifiers, duplicate computation, constraints, policies, report redaction/escaping/limits and restart recovery.

UI additions cover combined assessment, Reports view reuse, confirmation cancellation with no write, numeric JSON protection before serialization, debounced recording filtering, owner-project navigation, in-page export failures and downloading actual response bytes. The existing request test now confirms POST explicitly; invalid bodies disable Send before execution. Final DOM test output reported no test failures. These tests do not establish real browser console/layout/clipboard behavior.

## Performance evidence

Same service-fixture workload, measured SQL SELECT statements for a paginated compatibility history request:

| Stored runs | Before | Final |
| --- | --- | --- |
| 2 | 12 | 8 |
| 10 | 44 | 8 |

Policies and comparison rules now load once per page, and source IDs are validated in one batch without fetching full response bodies. Recording summaries select only returned summary columns. Text searches debounce by 200 ms. No latency, throughput, memory, concurrent-load or general large-dataset benchmark is claimed; query-count results apply to this tested workload.

## Remaining environment checks

- **Docker build/start/restart:** Docker is absent. Images, actual Compose orchestration/networking and named-volume lifecycle have not been executed here. Static checks and native persistence are useful evidence but do not satisfy the Docker acceptance item.
- **Browser/visual/mobile/download:** a fresh Chromium launch failed before opening a page: process-singleton `socket()` returned `Operation not permitted` (exit 134). The six Playwright tests are present but unexecuted. No screenshots, real-browser console pass, responsive-layout pass or browser download pass is claimed.
- **PostgreSQL 17 image:** Compose specifies 17; available native verification used 16.2.
- **External authenticated HTTPS:** no third-party target was exercised. Actual connection policy/Host/SNI and temporary-secret behavior have automated regression coverage.
- **Dependency audit/load testing:** no fresh vulnerability-database audit or load/stress benchmark was performed. One nonfatal Starlette test-client warning recommends HTTPX2; the tested runtime keeps its existing HTTPX pin. npm also emitted an environment-proxy configuration warning, not a build/test failure.

## Finish the two acceptance checks locally

From the project root, with Docker installed:

```sh
docker compose config
docker compose up --build
```

Then, in another terminal:

```sh
python scripts/release_demo.py
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

The browser tests create sample projects. Use a development instance. For a native stack, set `E2E_TARGET_URL=http://127.0.0.1:8001` and `E2E_REPLAY_TARGET_URL=http://127.0.0.1:8004`; `E2E_BASE_URL` defaults to `http://127.0.0.1:5175`. `CHROMIUM_PATH` may point to a local system browser. Optional `SCREENSHOT_DIR` must name an existing directory. Review desktop and 390px layouts, the paired response panels, expanded findings, policy errors and both exported formats.

Stop with `docker compose down`, start again without deleting volumes, and reopen the saved report URL. This verifies the remaining container persistence item on the actual destination.

[Completion report](PHASE5.md) · [Demo](DEMO.md) · [Security design](SECURITY.md)

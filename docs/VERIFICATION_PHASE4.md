# Phase 4 verification report

Verified on **18 November 2026**. Implementation and automated/live checks are complete as described below. Docker startup and actual browser execution remain open environment checks.

| Check | Observed result | Scope |
| --- | --- | --- |
| Full backend suite | **203 passed** | PostgreSQL 16.2, isolated per-test schemas; all 142 prior tests plus 56 compatibility-rule tests and 5 compatibility API workflows |
| Migration final check | **1 passed** | Reran the extended migration test on a separate empty PostgreSQL database after adding seeded Phase 3 comparison/difference/settings preservation checks |
| Frontend interaction suite | **19 passed** | Four jsdom test files: all 14 prior tests plus 5 compatibility workflows |
| TypeScript + production bundle | **Passed** | `npm run build`; Vite 6.4.6, 1,669 modules; JS 333.38 kB (gzip 100.35 kB), CSS 44.75 kB (gzip 10.39 kB) |
| Live Phase 1/2 regressions | **Passed** | Existing capture and replay smoke scripts; independent native sample APIs, backend and PostgreSQL |
| Live Phase 3 regression | **Passed** | Thirteen fixtures, repeated-header/status/body changes, explicit ignore/unordered rules and retained comparison history |
| Live Phase 4 workflow | **Passed** | Ten v1/v2 fixtures through Vite proxy → backend → PostgreSQL; compare → analyze → policy edit → reanalyze → history → exports |
| Explicit-contract results | **Passed** | Zero confirmed findings before policy; four after the example policy: required path, type, HTTP status and required header |
| Coverage/outcomes | **Passed** | Fixture session: 10 compared, 1 identical, 8 changed, 4 confirmed findings, 2 unassessed findings and 1 real transport timeout, distinct from HTTP 500 |
| Reproducibility | **Passed** | Same effective configuration reuses IDs; reverting policy reuses original analysis/run; historical reports unchanged after policy updates |
| Source immutability | **Passed** | Full original, replay-result and comparison API payloads unchanged after analysis/reanalysis |
| Initial Phase 3 → 4 migration | **Passed** | Preserved 65 recordings, 13 replay sessions, 41 results, 30 comparisons, 36 differences and 2 comparison-settings rows |
| Migration round trip | **Passed** | Seed Phase 1 records, Phase 2 session/result, Phase 3 comparison/difference/settings; upgrade to Phase 4, downgrade to Phase 3 and re-upgrade without changing source rows; earlier downgrade paths also checked |
| Alembic metadata check | **Passed** | `alembic check` reports no new upgrade operations detected |
| Process restart | **Passed** | Exact historical run details and JSON report content survived backend restart; existing replay and comparison history also unchanged |
| OpenAPI | **Passed** | All 12 compatibility operations present; application version 0.4.0 |
| Python static checks | **Passed** | Ruff `F` checks over backend, sample API and scripts |
| Compose static inspection | **Passed** | Five services, YAML/build paths/dependencies, retained volume, backend migration startup and loopback-only published ports |
| Playwright discovery | **5 tests discovered** | Four files; includes compatibility policy/evidence/history/download journey. Discovery is not browser execution. |

## What the tests establish

Pure tests cover rule trigger/non-trigger cases, explicit-contract precedence, severity/confidence/templates, JSON typing including booleans versus numeric values and optional type constraints, successful/error status handling, required headers/media types, dynamic values, ignored paths, masked ancestors, unsupported/omitted responses, transport gaps, deterministic results, preview/finding limits, unknown change types, pre-existing violations, pointer/media/header/status validation, canonical policy hashes, duplicate endpoints, verdict priority and unordered arrays without invented item identity.

API tests exercise record → replay → compare → analyze, policy changes, exact historical reads, current-result selection, source integrity, idempotency/reversion, session aggregation, literal filters/pagination, missing comparisons, running-session rejection, actual mocked connection failures, report escaping/redaction/caps, invalid IDs and cross-project source inconsistencies. Database uniqueness handles concurrent duplicate inserts; no concurrent load/stress benchmark is claimed.

The live test uses separate v1/v2 sample processes and real HTTP. The ten fixture paths are documented in `PHASE4.md` and the example policy is in `examples/compatibility-policies.json`. The timeout fixture really waits longer than the configured capture timeout. Reports are retrieved as JSON and HTML over the Vite API proxy. Further live checks captured plain text, a real HTTP 302 without following it, and a timeout. No source snapshots were rewritten.

DOM tests verify scoped verdict/count rendering, classification/severity/method/endpoint/search filters, expanded evidence and exact difference links, frozen policy disclosure, JSON validation, server validation with draft retention, saving without automatic reanalysis, explicit reanalysis/new historical result, JSON/HTML download URLs, empty states and retry. Browser downloads, layout and visual correctness are not established by jsdom.

One nonfatal upstream warning remains: Starlette's test client deprecates its HTTPX adapter in favor of HTTPX2. Tests passed using the project's existing pinned HTTPX dependency. There are no new application dependencies. No fresh dependency security audit or performance benchmark is claimed.

## Unverified checks

- **Docker build and Compose startup:** Docker is not installed. The actual container lifecycle, images, health-check orchestration and Docker networking were not executed. Static inspection and native live verification do not replace this check.
- **Real browser and mobile layout:** A Chromium launch in this environment on 18 November failed before opening a page because process-singleton socket creation was denied (`Operation not permitted`). The five runnable Playwright tests are included, but no actual browser, screenshot, responsive-layout, clipboard or browser-download pass is claimed here.
- **PostgreSQL 17 container image:** Compose specifies PostgreSQL 17; the available native verifier was PostgreSQL 16.2.
- **External authenticated HTTPS targets:** No third-party authenticated endpoint was exercised. Existing URL/IP/Host/SNI and credential-redaction tests remain in the regression suite.

## Acceptance status

| Requirement | Status |
| --- | --- |
| Previous capture/replay/comparison phases | Automated and native live regression checks pass |
| Deterministic classifications, evidence, severity/confidence and actions | Implemented; rule/API/fixture checks pass |
| Project endpoint policies, session verdicts, PostgreSQL persistence/history | Implemented; API/live/migration/restart checks pass |
| Overview, filtering, evidence, editor and historical UI | Implemented; DOM tests pass; real browser/visual validation pending |
| JSON and HTML reports | Implemented; API/live escaping/redaction/limits/reproducibility checks pass; browser download test included but unexecuted |
| Ten fixture scenarios and manual demonstration | Verified through native services; documented |
| Docker Compose starts successfully | **Unverified — run locally with Docker** |
| README, file map, API/rule catalogue, migration details and Phase 5 proposal | Included |

## Finish the environment checks locally

Keep the existing `.env` and database volume. From the extracted project folder:

```sh
docker compose config
docker compose up --build
```

In another terminal with Python available:

```sh
python scripts/smoke_test.py
python scripts/replay_smoke_test.py
python scripts/comparison_smoke_test.py
python scripts/compatibility_smoke_test.py
cd frontend
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

The scripts/tests create development projects and saved evidence. Use a development database. Native target options are documented in README. Review Compatibility at desktop and mobile widths, exercise expanded findings and policy errors, follow exact difference links, download both report formats, restart without removing the volume, and reopen historical analyses.

[Phase 4 implementation and demo](PHASE4.md) · [Phase 3 verification archive](VERIFICATION_PHASE3.md) · [Phase 2 verification archive](VERIFICATION_PHASE2.md)

# Phase 3 verification report

Verified on 18 November 2026. This report distinguishes implemented features from checks executed in this environment.

| Check | Result | Evidence and scope |
| --- | --- | --- |
| Backend suite | **142 passed** | Final run against PostgreSQL 16.2 with isolated per-test schemas; includes all Phase 1/2 tests, 38 pure comparison tests and 5 comparison API/integration tests |
| Frontend DOM suite | **14 passed** | All three test files: existing capture/replay flows and five new comparison workflows |
| TypeScript and production build | **Passed** | Final `npm run build`; Vite 6.4.6, 1,664 transformed modules |
| Live capture and replay regression | **Passed** | Existing Phase 1 and Phase 2 smoke scripts against independent native services and real PostgreSQL |
| Live comparison flow | **Passed** | Vite proxy → backend → PostgreSQL; thirteen deterministic v1/v2 fixtures recorded, replayed, compared and retrieved |
| Rules and reproducibility | **Passed** | Timestamp ignore and unordered-array rules produce expected results; old comparisons retain their differences and settings; matching rules reuse IDs |
| Source immutability | **Passed** | Full original/replay API payloads compared before and after calculation |
| Restart persistence | **Passed** | Exact comparison details and replay history remained identical after backend process restart |
| Existing Phase 2 upgrade | **Passed** | Initial 0002→0003 migration preserved 19 recordings, 3 sessions and 5 replay results; subsequent runs at head also preserved existing rows |
| Migration round trip | **Passed** | Dedicated empty PostgreSQL database: seed Phase 1 records, upgrade to Phase 2 and seed a session/result, upgrade/downgrade Phase 3, verify preserved data and upgrade again |
| Alembic schema comparison | **Passed** | `alembic check`: no new upgrade operations detected |
| OpenAPI | **Passed** | Schema generated with version 0.3.0 and all nine comparison/configuration/history operations |
| Python static checks | **Passed** | Ruff `F` checks over backend, sample APIs and scripts |
| Compose static checks | **Passed** | Unique YAML keys, five services, build contexts, dependencies, loopback bindings and retained named volume |
| Browser test discovery | **Passed** | Four Playwright tests found across capture, replay and comparison files; discovery is not test execution |

## Coverage details

The pure algorithm tests cover object-order independence, nested objects/arrays, additions/removals, scalar and type changes, booleans versus numbers, large integers without decimal-context rounding, numeric formatting equivalence, missing/null/empty distinctions, escaped/empty property names, index-based order, unordered multiset multiplicity, exact ignore rules, invalid rules, status codes, case-insensitive and repeated headers, ignored volatile headers, text/HTML treated as text, unsupported/truncated/failed captures, masked values, deterministic ordering, bounded previews, and size/depth/node/difference/path limits.

API tests cover persisted summaries/differences, idempotency, unchanged originals/replays, defaults, one-off settings, rule updates, stale history, current-result selection, session aggregation, pagination, invalid/missing IDs, cross-project integrity, pending results, transport failures, repeated headers, secret sanitization and complete-value retrieval by source reference. Database uniqueness constrains concurrent identical calculations; a concurrent load/stress test was not performed.

The live smoke script exercises all thirteen sample cases: unchanged, added, removed, value, type, nested, array, status, headers, timestamp, text, empty and unordered. It confirms 15 historical calculations after recalculating two cases with new rules, without creating duplicate calculations for repeated settings.

Frontend DOM tests verify session summary counts, explicit calculation, history reopening, highlighted labels, filter/search behavior, expanded values, difference navigation, rule validation/saving, older-settings warnings, recalculation, unavailable execution data, error retry and empty states. These use jsdom and a mocked API; they do not prove browser layout or actual clipboard behavior.

One nonfatal upstream warning appeared: Starlette's test client deprecates its HTTPX adapter in favor of HTTPX2. The suite passes with this project's pinned HTTPX dependency. No new runtime dependencies were added, and no fresh dependency vulnerability audit is claimed for Phase 3.

## Unverified or blocked

- **Docker builds and Compose startup:** Docker is not installed in this environment. Configuration was checked statically; the five-container lifecycle and Docker networking were not executed.
- **Real-browser and visual/mobile checks:** A fresh Chromium launch attempt on 18 November failed before a page could open: its process singleton's socket creation was denied with `Operation not permitted`. No browser test, screenshot, visual layout, synchronized scrolling or clipboard pass is claimed. The four runnable browser tests are included for local execution.
- **PostgreSQL 17 image:** Compose configures PostgreSQL 17; native verification used the available PostgreSQL 16.2 executable.
- **External authenticated HTTPS APIs:** No third-party authenticated target was exercised. Existing destination/Host/SNI/security tests remain included.

## Acceptance status

| Requirement | Status |
| --- | --- |
| Preserve capture/replay functionality | Existing automated and live regression checks pass |
| Deep JSON, array, status, header and text comparison | Algorithm/API/live fixture checks pass |
| Ignore rules and reproducible recalculation | Automated and live checks pass |
| Persist comparisons and reopen history | PostgreSQL, DOM remount and backend restart checks pass |
| Non-destructive migration | PostgreSQL migration/round-trip checks pass |
| Highlighting, filtering, navigation and rules UI | Implemented and DOM verified; visual/browser execution pending |
| Sample APIs and manual demo | Thirteen deterministic fixtures and live script verified |
| Docker Compose starts all services | **Needs local Docker validation** |
| README and detailed completion report | Included in README and PHASE3.md |

Phase 3 implementation is packaged for local validation. Full acceptance is not represented as closed while Docker startup and real-browser checks remain unverified.

## Finish the remaining checks locally

Keep your existing `.env` and named database volume. From the project folder:

```sh
docker compose config
docker compose up --build
```

In another terminal:

```sh
python scripts/smoke_test.py
python scripts/replay_smoke_test.py
python scripts/comparison_smoke_test.py
cd frontend
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

These scripts/tests create development projects, recordings, sessions and comparisons. Use a development database. Native target options are documented in README.

Open http://localhost:5175, follow the [Phase 3 demonstration](PHASE3.md#repeatable-demonstration), and inspect the comparison viewer at desktop and mobile widths. Verify expansion, navigation, copying, synchronized scrolling, rules and old/new history. Restart the stack without removing its volume and reopen both historical and current comparisons.

[Phase 2 verification archive](VERIFICATION_PHASE2.md)

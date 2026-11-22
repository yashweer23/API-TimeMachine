# Phase 3 — Deterministic response comparison

Phase 3 compares saved original/replay responses, persists structured differences, and adds a Comparisons workspace. Comparing never makes another outbound request. Phase 1 capture and Phase 2 replay remain available. This phase describes observed differences; it does not classify API compatibility or breaking changes.

## Upgrade and startup

Keep your existing `.env`, database password, and `postgres_data` volume. Copy the Phase 3 source into the same project folder and run:

```sh
docker compose up --build
```

Open http://localhost:5175. Startup applies `0003_comparisons` after the previous migrations. No new services, libraries, credentials, or target origins are required. If upgrading directly from Phase 1, also follow [the Phase 2 upgrade notes](PHASE2.md#upgrade-an-existing-phase-1-project) to approve sample v2.

Native development uses the existing four-terminal setup. From `backend`, run `python -m alembic upgrade head` before starting it. The sample v2 target is `http://127.0.0.1:8004` in native mode and `http://sample-api-v2:8001` in Docker.

### Database migration

The migration adds three tables without altering the existing project, recording, session, or replay-result rows:

| Table | Stored information |
| --- | --- |
| `project_comparison_settings` | Current project rules and update time |
| `comparisons` | Replay-result reference, status, HTTP codes, counts, effective rules, rules hash, algorithm version, notes and timestamp |
| `comparison_differences` | Ordered differences: scope, JSON Pointer, change type, old/new types, presence flags, bounded values/previews and truncation flags |

Foreign keys, ordered relationships, uniqueness constraints, status/scope/count constraints, and lookup indexes are included. JSON fields use PostgreSQL JSONB. Explicit presence flags distinguish missing values from JSON null even when both stored value columns are SQL null.

A unique constraint on `(replay_result_id, algorithm_version, rules_hash)` makes repeated and concurrent calculations idempotent. Recalculation with different rules creates a separate comparison; earlier results keep their effective settings. Returning to a prior configuration reuses its existing result and timestamp. Changing project defaults alone does not rewrite history.

Downgrading to `0002_replay_sessions` removes comparison history/settings, while retaining Phase 1/2 captures and replays. Do not downgrade just to restart the app.

## Algorithm and difference semantics

The implementation is pure Python, deterministic, and does not use an LLM. It operates on sanitized saved snapshots.

1. Check combined input size, node count and nesting before comparison.
2. Validate source/project relationships. Pending/running replay results are not compared or cached.
3. Normalize header names and preserve repeated values as ordered lists. Apply the saved ignore rules.
4. Compare HTTP status, then headers in sorted name order, then the body in deterministic depth-first order.
5. Recursively compare JSON objects by sorted property names. Missing properties have an explicit sentinel separate from null. Booleans remain distinct from numbers. Numeric comparisons use exact normalized decimal tuples of the stored parsed values, without tolerance or decimal-context rounding; `1` and `1.0` are equivalent.
6. Compare arrays by index unless their exact path is configured as unordered. A type change emits one parent record, without redundant child records.
7. Compare text as text, including HTML/XML. A text difference contains old/new content or references to complete values; text is never reparsed as JSON.
8. Persist bounded difference records and the effective configuration. Original/replay responses are unchanged.

Confirmed change types: `field_added`, `field_removed`, `value_changed`, `type_changed`, `array_changed`, `status_changed`, `header_added`, `header_removed`, `header_changed`, `text_changed`. A removed `name` and added `full_name` are independent facts; the engine does not infer a rename.

Array insertions/removals use precise index paths and presence flags. Reordering is significant by default. An unordered-array rule compares exact multisets, including duplicate multiplicities and nested values. If those multisets differ, one `array_changed` record represents the whole array; no speculative identity matching is performed.

### Paths and rules

Rules use **exact JSON Pointer**, not JSONPath expressions or executable code:

| Meaning | Rule |
| --- | --- |
| Property `generated_at` | `/generated_at` |
| Nested city | `/profile/address/city` |
| Second array element | `/roles/1` |
| Literal property `a/b` | `/a~1b` |
| Literal property `~key` | `/~0key` |
| Empty property name | `/` |
| Entire body | Empty string in API; `(root)` on its own line in the UI |

Ignoring an object/array path ignores that subtree. Paths absent from a particular response are harmless. Wildcards and expression evaluation are not supported; `*` is a literal property name. Rules inside an unordered array, including nested unordered rules, are rejected because indexes lose a stable meaning there. Keep index-based comparison if you need child-specific rules.

Example project configuration:

```json
{
  "ignored_json_paths": ["/generated_at"],
  "ignored_headers": ["date", "server-timing", "traceparent", "tracestate", "x-correlation-id", "x-request-id", "x-trace-id"],
  "unordered_array_paths": ["/roles"]
}
```

The default ignored-header list is exactly the seven headers above. It is visible and editable. `Content-Type`, `Content-Length`, and other nonlisted headers remain compared. Body changes can therefore also produce a legitimate Content-Length header difference. Sensitive values are always sanitized, regardless of ignore settings.

Limits for rule configuration: 50 ignored body paths, 50 ignored headers, 20 unordered-array paths; path length 2,048 characters and at most 64 segments. Duplicate entries and header-name casing normalize before hashing.

### Incomplete and unavailable data

| Comparison state | Meaning |
| --- | --- |
| `identical` | No differences in the observable responses under the saved rules |
| `different` | Complete comparison with confirmed differences |
| `partial` | Status/headers or other observable data compared, but a body or masked value was not comparable |
| `unavailable` | A transport failure, missing HTTP response, or invalid input prevents meaningful response comparison |
| `limited` | A work/output limit was reached; counts describe retained differences only |

HTTP 400/404/500 are real responses and can be compared. Timeouts, connection failures, interruption and unexecuted requests are not invented HTTP statuses. Execution errors remain available in the paired viewer and the linked replay page.

Empty HTTP bodies differ from JSON null and from text or JSON empty strings/arrays/objects. Unsupported binary, omitted, or incomplete bodies are not treated as empty. The recorder omits over-limit bodies entirely; it does not persist a truncated prefix. For an older/imported capture identified as truncated, Phase 3 conservatively compares only available status/headers and reports a partial result.

Matching `[REDACTED]` markers do not prove hidden values are equal. Masked leaves are excluded and comparisons are marked partial. Added/removed fields can still be reported by presence without revealing hidden contents. Never treat partial, limited, or unavailable results as successful equivalence checks.

## API endpoints

POST comparison requests use JSON `{}` for current project defaults or `{"rules": {...}}` for a one-off effective configuration. POST returns `200` for both a new and a reused calculation.

| Method | Endpoint | Response |
| --- | --- | --- |
| POST | `/api/replay-results/{id}/compare` | Calculate/reuse a single comparison and return its differences |
| GET | `/api/replay-results/{id}/comparison` | Current-settings comparison if available; otherwise the latest historical result, flagged stale |
| POST | `/api/replay-sessions/{id}/compare` | Compare finalized results; reuse matching calculations and report pending requests separately |
| GET | `/api/replay-sessions/{id}/comparisons` | Applicable per-result summaries and session totals |
| GET | `/api/projects/{id}/comparison-settings` | Current rules, hash and timestamp |
| PUT | `/api/projects/{id}/comparison-settings` | Validate and replace project defaults |
| GET | `/api/projects/{id}/comparisons` | Paginated history of all saved configurations (`limit`, `offset`) |
| GET | `/api/comparisons/{id}` | Exact historical comparison and differences |
| GET | `/api/comparisons/{id}/differences/{difference_id}/values` | Complete sanitized old/new values resolved from immutable source records |

Malformed rules/IDs return 422, missing resources return 404, and unsettled results or inconsistent project relationships return 409. Current rules are normalized before hashing. Algorithm version is `pointer-v1`.

Session totals separate identical, different, and incomplete/unavailable comparisons. Partial and limited comparisons may contain confirmed differences; their retained difference counts are included without claiming completeness. Histories are paginated, sessions are bounded by Phase 2 limits, and source relationships are eager-loaded for batch comparisons.

## Frontend

The existing dark workspace now includes **Comparisons** in navigation and **Compare saved responses** on each replay session.

- **Overview:** select a session, calculate explicitly, see compared/identical/different/incomplete totals and category counts, then open a request.
- **Difference explorer:** filter by change category, search JSON Pointers, expand old/new values, and distinguish Missing from JSON null.
- **Paired inspector:** expandable JSON trees with green additions, red removals, amber modifications, purple type changes, and text labels. It includes previous/next difference navigation, status/header/body views, copy buttons and optional proportional synchronized scrolling. Text/HTML/XML renders as escaped text.
- **Rules:** edit one path/header per line, save defaults, and explicitly recalculate. Historical results show an older-settings notice when appropriate.
- **History:** reopen exact comparison IDs across refreshes and restarts, including calculations made with earlier rules.

The layout and interactions are implemented and covered by DOM tests. Real-browser visual/mobile inspection remains an explicitly unverified check in this environment; see [VERIFICATION.md](VERIFICATION.md).

## Repeatable demonstration

1. Create/select the sample v1 project, targeted at `http://sample-api:8001`.
2. Record `GET /regression/type`, `GET /regression/nested`, and `GET /regression/timestamp`.
3. Replay those recordings against `http://sample-api-v2:8001`.
4. Click **Compare saved responses**, then **Compare session**. Open each result and filter/expand its differences.
5. In project rules, add `/generated_at` to ignored JSON paths and save.
6. Open the timestamp comparison and choose **Recalculate with current rules**. It becomes identical; its earlier changed result stays in history.
7. Try `/regression/unordered`, then add `/roles` to unordered-array paths and recalculate.
8. Refresh and restart the application without removing its database volume. Reopen both old and new comparisons.

| Fixture (`/regression/…`) | Intentional case |
| --- | --- |
| `unchanged` | Identical object |
| `added` | Added `/enabled` |
| `removed` | Removed `/legacy` whose original value is null |
| `value` | Modified `/city` |
| `type` | Number-to-string `/age` |
| `nested` | Modified `/profile/address/city` |
| `array` | Modified `/roles/1` |
| `status` | HTTP 200 → 201, identical body |
| `headers` | Changed `X-Contract` and repeated `X-Feature` values |
| `timestamp` | Fixed, differing `/generated_at` values; no randomness |
| `text` | Changed plain-text line |
| `empty` | Identical HTTP 204 with empty body |
| `unordered` | Reordered roles, equal when explicitly order-insensitive |

Run the complete live demonstration with `python scripts/comparison_smoke_test.py`. Native mode accepts `--v1 http://127.0.0.1:8001 --v2 http://127.0.0.1:8004`; `--backend http://127.0.0.1:5175` exercises the frontend proxy too.

## Limits and implementation files

Work is bounded to 64 JSON levels, 50,000 visited input values, 2,200,000 combined serialized input bytes, 500 retained differences, and 4,096 bytes per emitted path. A difference stores values up to 2,048 bytes each; larger values have short previews and source references. Expand the row to fetch complete values. Comparison routes run in FastAPI's thread pool, not as queued background jobs. Large tree child lists render incrementally.

New captures preserve repeated response-header values as lists. Phase 1/2 already flattened repeated headers into comma-joined strings, so their original boundaries cannot be recovered; those legacy strings remain opaque and are not guessed apart. No full byte-for-byte HTTP transcript is claimed. JavaScript can display very large JSON numbers with reduced precision; authoritative differences are calculated on the backend, and previews preserve their serialized values.

| File/group | Change |
| --- | --- |
| `backend/app/services/comparison_engine.py` | Pure recursive comparison, uncertainty handling and limits |
| `backend/app/services/comparison_service.py` | Rules, persistence, history, batch queries and idempotency |
| `backend/app/models/comparison.py` | Three new tables |
| `backend/app/schemas/comparison.py` | Validated rules and typed contracts |
| `backend/app/api/comparison_routes.py` | Nine comparison/configuration/history routes |
| `backend/alembic/versions/0003_comparisons.py` | Non-destructive Phase 3 upgrade |
| `backend/app/services/recorder.py` | Preserve repeated response headers for new captures |
| `frontend/src/pages/Comparisons.tsx`, `ComparisonDetails.tsx` | Session overview, history and detailed inspection |
| `frontend/src/components/comparison/` | Rules panel, difference explorer, highlighted JSON viewer |
| `frontend/src/services/comparisonApi.ts`, `types/comparison.ts` | Typed client and interfaces |
| `frontend/src/App.tsx`, `styles.css`, replay detail page | Navigation, comparison link and matching visual styles |
| `backend/tests/test_comparison_engine.py`, `test_comparisons.py`, `test_migrations.py` | Algorithm/API/security/history/migration checks |
| `frontend/src/tests/comparison.test.tsx`, `e2e/comparison.spec.ts` | DOM tests and locally runnable browser flow |
| `sample-api/main.py`, `scripts/comparison_smoke_test.py` | Thirteen deterministic cases and live verification |

The application remains a local, single-user tool. No authentication, compatibility scoring, severity classification, AI, CI integrations, scheduling, or deployment was added. [Phase 4 implementation](PHASE4.md) · [Phase 3 verification archive](VERIFICATION_PHASE3.md)

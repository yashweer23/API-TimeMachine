# Phase 4 — Breaking-change intelligence and compatibility reports

Phase 4 adds a deterministic assessment of **saved Phase 3 comparisons**, explicit endpoint requirements, immutable analysis history, an evidence explorer, and JSON/self-contained HTML reports. No LLM, consumer discovery, numerical risk score, scheduler, or CI integration is used. Recording, replay and neutral comparison remain available.

## Upgrade and migration

Keep the existing `.env` and PostgreSQL volume. Replace project source with this version and run `docker compose up --build`. Backend startup runs `alembic upgrade head`. Native development: from `backend`, run `python -m alembic upgrade head` before starting the server. No new environment variables or dependencies are required.

Migration **`0004_compatibility`**, in `backend/alembic/versions/0004_compatibility.py`, adds five tables:

| Table | Purpose and constraints |
| --- | --- |
| `project_compatibility_policies` | One validated endpoint-policy bundle per project, project FK, update time. Saving replaces the bundle atomically. Endpoint method/path pairs are unique within the bundle. |
| `compatibility_analyses` | Immutable per-comparison assessment, project/session/comparison FKs, endpoint, policy and comparison-rule snapshots, engine version, counts, verdict, time. Unique `(comparison_id, engine_version, policy_hash)`. |
| `compatibility_findings` | Analysis FK, optional original difference FK, stable ordinal, classification, severity/confidence, explanation/action/rule and bounded evidence. Unique `(analysis_id, ordinal)`; enum/count constraints; filtering index. |
| `compatibility_runs` | Immutable session composition, frozen project/session/source/target metadata, aggregate counts, missing comparison IDs and verdict. Unique `(session_id, engine_version, fingerprint)`; project/date index. |
| `compatibility_run_items` | Ordered run-to-analysis relationship, FKs and ordinal constraint. |

Existing source tables are not altered. Downgrading to `0003_comparisons` removes Phase 4 data only; it preserves recordings, replays, comparison settings and differences. Do not downgrade a database containing analyses you intend to keep.

## Evidence model and classification

Every finding records a UUID, source comparison and optional difference UUID, method/path, JSON Pointer or component, detected change, classification, severity, confidence, title, deterministic explanation, action, rule ID, safe old/new previews, an explicit requirement when applicable, and whether a contract violation was already present in the baseline.

| Classification | Meaning |
| --- | --- |
| `confirmed_breaking` | A saved replay violates a **supplied explicit contract**. This does not prove any particular consumer executed or failed. |
| `potentially_breaking` | Structural/media/HTTP evidence suggests risk, but a consumer requirement is not established. |
| `informational` | An explicit policy permits the change, or a documented low-confidence default treats it as informational. |
| `unassessed` | Evidence, context or a supported rule is insufficient. It is not a synonym for compatible. |

Precedence is explicit contract → explicit permission → default heuristic → unassessed. Contract checks inspect the immutable saved responses for specific requirements even when Phase 3 ignored a path. They do **not** generate a second general diff. A finding from an ignored path or pre-existing contract violation can have no associated difference ID; the UI links its source comparison instead.

An unchanged response may still violate a newly supplied contract. Such findings explicitly state that the baseline also violated it; the tool does not claim that the replay introduced the violation. Matching contract findings suppress redundant default judgments on the same difference; multiple explicit requirements can legitimately produce separate findings.

## Policies

Open **Compatibility → Endpoint compatibility policies**. Edit the validated JSON bundle and select **Save policies**, then explicitly select **Analyze session**. Saving never rewrites analyses. A complete working fixture bundle is in [`examples/compatibility-policies.json`](../examples/compatibility-policies.json).

```json
{
  "endpoints": [{
    "method": "GET",
    "endpoint_path": "/users/1",
    "expected_status_codes": [200],
    "required_json_paths": ["/data/id"],
    "expected_types": {"/data/id": "integer"},
    "required_headers": ["content-type"],
    "allowed_content_types": ["application/json"],
    "allow_additional_fields": true,
    "dynamic_json_paths": ["/generated_at"]
  }]
}
```

Policies match a method and **exact recorded endpoint path**; query parameters, request body variants, route templates and wildcards are not matched separately. Different query inputs at the same method/path share its policy. Maximum 50 endpoint policies. Unknown fields and duplicate endpoint keys are rejected. Header names are case-insensitive. Media types are exact, case-insensitive, without parameters; response charset parameters are ignored during validation. Expected successful statuses are integers 200–299; an empty list means unspecified, not “any response is successful.”

Paths use JSON Pointer: `/profile/name`, `/items/0/id`, `~1` for `/`, `~0` for `~`, and `""` for the root. Maximum 50 required paths, 50 type declarations, 50 dynamic paths, 50 headers and 20 media types per endpoint; path length/depth are bounded. No expression evaluation occurs.

Types are `object`, `array`, `string`, `number`, `integer`, `boolean`, `null`. Boolean is not numeric. Integral JSON numbers such as `1.0` satisfy `integer`. Type requirements apply to present paths; declare a path required separately if omission must be a violation. A masked scalar cannot prove its original type, and a masked ancestor cannot prove child absence. JSON null is present; a known empty HTTP body has no root JSON value. Non-JSON/omitted/incomplete captures are unassessed for JSON contract checks.

`allow_additional_fields: false` prohibits **new object properties relative to the recorded baseline**, including nested properties. It is not a full closed schema and does not prohibit new array elements by itself. Ordered arrays use index positions. Within an unordered array, additions cannot be matched by invented item identity: changed unordered evidence becomes unassessed for this check. `true` explicitly permits property additions; `null`/omission uses the default low-confidence informational rule with a strict-consumer caveat.

Dynamic paths permit value changes at that path or its descendants. They never excuse removals, type changes, array membership changes, or other structural changes. Required/type constraints take precedence. An ignored JSON path with changed evidence remains an evidence gap unless an explicit dynamic policy covers it and shape/types are unchanged. Default ignored volatile headers are tolerated metadata; user-ignored changed semantic headers create gaps. Phase 3 partial/limited/unavailable states remain incomplete even when some contract violations can be confirmed.

## Rule catalogue

Severity and confidence are separate from classification. Severity is a documented impact category, not a computed risk score. Confidence describes the strength of the evidence for this judgment, not the probability of a consumer failure. Unassessed evidence has **no severity rating** and low confidence.

| Rule | Trigger | Class | Severity / confidence |
| --- | --- | --- | --- |
| `contract.required_path` | Explicit required path absent in a complete replay body | Confirmed | Critical for root, otherwise high / high |
| `contract.type` | Present JSON value violates explicit type | Confirmed | Critical for root, otherwise high / high |
| `contract.status` | Replay status outside declared successful codes | Confirmed | High for HTTP errors, otherwise medium / high |
| `contract.required_header` | Declared required header absent | Confirmed | High / high |
| `contract.content_type` | Missing or disallowed declared media type | Confirmed | Medium / high |
| `contract.additional_field` | Object property added while explicitly prohibited | Confirmed | Medium / high |
| `policy.allowed_status`, `policy.allowed_content_type` | New value belongs to explicit allowlist | Informational | Low / high |
| `policy.dynamic_value` | Value change permitted by dynamic path; structure/type unaffected | Informational | Low / high |
| `policy.additional_allowed` | Object property added with explicit permission | Informational | Low / high |
| `heuristic.error_status` | Replay HTTP 4xx/5xx without a successful-status contract | Potential | High / medium |
| `heuristic.field_removed` | Removal with no confirming requirement | Potential | Medium / medium |
| `heuristic.type_changed` | Type change with no confirming requirement | Potential | High / medium |
| `heuristic.array_changed` | Unordered array membership changes | Potential | Medium / low |
| `heuristic.header_removed`, content-type header change | Header removal or media change without an explicit allowlist | Potential | Medium / low |
| `default.field_added` | New object property, no declared additional-field policy | Informational with strict-consumer caveat | Low / low |
| `default.header_metadata` | Added header or changed content-length | Informational | Low / low |
| `default.unassessed` | Ordinary value/text/boolean changes, unsupported change types, undeclared successful-status transitions or generic header-value changes | Unassessed | Not rated / low |
| `evidence.*` | Missing HTTP, capture/comparison gaps, redacted contract evidence, changed ignored paths/headers, ambiguous unordered additions, assessment limits | Unassessed | Not rated / low |

For a repeated HTTP error without a contract, the explanation identifies that the baseline also had an error. Transport failures do not become synthetic 500 statuses or contract-status violations.

## Session verdicts, coverage and reproducibility

Analysis reads finalized sessions only; a running session returns 409. Compare the session first. Missing comparisons are recorded as coverage gaps; analysis does not implicitly rerun Phase 3 or contact the API. For each result it uses a comparison matching current Phase 3 rules when available, otherwise the latest saved comparison, with its historical rules clearly shown.

Verdict priority:

1. Any confirmed finding: **Incompatible with configured contract**.
2. Otherwise any potential finding: **Potential compatibility issues**.
3. Otherwise any unassessed finding, missing comparison, incomplete coverage or empty assessment: **Insufficient evidence**.
4. Otherwise: **Compatible under configured policy**.

A confirmed or potential verdict may coexist with incomplete coverage; all gap counts remain visible. Compatible never means universal API safety. Identical is a Phase 3 observation and does not imply an explicit contract is satisfied.

Summary counts include total requests, replay attempts, compared/identical/changed requests, incomplete/missing comparisons, execution/transport failures, four finding-class counts, high/critical findings and retained findings. Classification counts are findings, not unique requests. A missing comparison increments coverage counts without manufacturing a source finding.

Policy JSON is canonicalized and hashed. An analysis is deduplicated by source comparison, rule-engine version (`compatibility-v1`) and effective endpoint policy hash. A run is deduplicated by its ordered analysis IDs, missing-result IDs and engine version. Reverting a policy can reuse the original historical result. Changing an unrelated endpoint policy does not force new analyses. Unique constraints also handle simultaneous identical analysis inserts. History retains timestamps and frozen policy/rule/metadata snapshots. The GET current endpoint prefers a run matching available comparisons and effective policies, falling back to the latest historical run. Exact IDs always resolve historical results.

## API endpoints

All routes are under `/api`. POST bodies are `{}` with `Content-Type: application/json`. PUT accepts the policy bundle above. Analysis never invokes outbound HTTP. UUIDs, policy data, filters and source/project relationships are validated.

| Method | Path | Result |
| --- | --- | --- |
| POST | `/comparisons/{comparison_id}/analyze` | Create/reuse a comparison assessment |
| GET | `/comparisons/{comparison_id}/compatibility` | Current matching or latest historical assessment |
| POST | `/replay-sessions/{session_id}/analyze` | Create/reuse immutable session run |
| GET | `/replay-sessions/{session_id}/compatibility` | Current matching or latest historical run |
| GET | `/compatibility-analyses/{analysis_id}` | Exact historical analysis |
| GET | `/compatibility-analyses/{analysis_id}/findings` | Paginated/filterable findings |
| GET | `/compatibility-runs/{run_id}` | Exact historical session run and analysis snapshots |
| GET | `/compatibility-runs/{run_id}/findings` | Findings across a session run |
| GET | `/compatibility-runs/{run_id}/report?format=json\|html` | Bounded historical download |
| GET | `/projects/{project_id}/compatibility-runs` | Paginated session analysis history |
| GET | `/projects/{project_id}/compatibility-policies` | Current validated bundle/hash/update time |
| PUT | `/projects/{project_id}/compatibility-policies` | Validate and replace current bundle |

Findings accept `classification`, `severity` (including `unrated`), `method`, `endpoint` (literal substring), `search` (literal path/title substring), `limit` (1–100, default 25) and `offset`. History defaults to 20 rows, max 100. Endpoint and title/path searches escape SQL wildcard characters. Empty pages are valid; unknown IDs return 404, invalid inputs 422, running or inconsistent source relationships 409. SQL failures use the existing safe error response.

## Interface

**Compatibility** is available in the sidebar and from session/individual comparisons. Choose a session, explicitly analyze it, inspect its scoped verdict and counts, filter findings by classification/severity/method/endpoint/path/title, and expand paired old/new previews with evidence strength, rule, requirement and recommended action. Links select the exact Phase 3 difference via `?difference=UUID`; coverage findings open the source comparison.

The JSON policy editor has a complete example, basic JSON validation, server validation messages and draft preservation on failure. Saving marks older analyses appropriately but does not silently reanalyze. Run history links exact IDs and displays session, date, verdict, counts and current/historical configuration. Frozen effective policies and Phase 3 rules remain inspectable. Download links point to the selected historical run.

## Reports and bounds

**JSON** is machine-readable; **HTML** is a self-contained printable report with executive summary, source/target/session/project, analysis time/version, evidence and recommendations, frozen policies and methodology. PDF generation is deferred. HTML uses no scripts/external assets, escapes all dynamic values, and applies a restrictive content security policy. Download names use a fixed prefix plus validated run UUID; responses use attachment disposition, `nosniff` and no-store caching.

Reports contain allowlisted assessment data and safe evidence previews, not request credentials, temporary overrides, environment configuration, raw requests or complete response bodies. URLs omit user-info, query strings and fragments. Key/pattern redaction is applied to snapshots and again to exports. As in earlier phases, arbitrary secrets embedded in endpoint paths, names, labels or otherwise unrecognizable values cannot be inferred: do not put secrets there. Required header names and JSON paths are configuration, not secret header values.

Limits: 600 findings per comparison (last slot reserved for an explicit incomplete-assessment finding), Phase 3 input bounds (64-depth/50,000 nodes/2.2 MB aggregate comparison input), 2,048-byte stored value limits with 500-character previews, 500 findings per report, JSON export 2 MB and HTML 4 MB. Reports state included and omitted counts; summaries cover all retained findings. Full saved findings remain available through paginated APIs. Oversized reports return 413. Dynamic “current” flags are excluded from report content so changing policies does not rewrite historical exports. Engine-limit counts represent retained findings only.

## Demonstration

1. Start the stack using the README. Create a sample project with v1 target `http://sample-api:8001` (native: `http://127.0.0.1:8001`).
2. Record the ten GET paths below. Replay them as one batch against `http://sample-api-v2:8001` (native: `http://127.0.0.1:8004`). Keep capture timeouts below 25 seconds for the timeout fixture.
3. From Replay, open Comparisons and select **Compare session**.
4. Open Compatibility, select the session and **Analyze session**. With no contract, there must be **zero confirmed findings**.
5. Expand policies, paste `examples/compatibility-policies.json`, save, then **Analyze session** again.
6. Expect four confirmed findings and an incompatible-with-contract verdict. Filter high-severity confirmed findings; expand evidence; open a saved Phase 3 difference.
7. Inspect the earlier run in history and its frozen policy. Download JSON and HTML from either historical run. Reload to verify persistence.

| Fixture path under `/compatibility/` | v2 behavior | Expected main finding with example policy |
| --- | --- | --- |
| `unchanged` | Same JSON | No finding; compatible within recorded scope |
| `required-removed` | Removes `/id` | Confirmed, high |
| `type` | `/age` number → string | Confirmed, high |
| `added` | Adds `/enabled` | Informational, explicitly permitted |
| `value` | Changes `/city` | Unassessed; no expected-value contract |
| `status` | 200 → 201 | Informational; both explicitly permitted |
| `error` | HTTP 500 | Confirmed, high; expected 200 |
| `header` | Removes `x-contract` | Confirmed, high |
| `timestamp` | Changes `/generated_at` | Informational, explicit dynamic path |
| `transport` | Waits 25 seconds | Transport timeout, unassessed; not HTTP 500 |

Content-length differences may add informational metadata findings. The fixture session has 10 compared, 1 identical, 8 changed, 4 confirmed findings, 2 unassessed findings, and 1 transport failure with default timeouts.

Automated live demonstration (creates development data):

```sh
python scripts/compatibility_smoke_test.py
# Native targets, through Vite's real API proxy:
python scripts/compatibility_smoke_test.py --backend http://127.0.0.1:5175 --v1 http://127.0.0.1:8001 --v2 http://127.0.0.1:8004
```

## Files created or modified

| Area | Files |
| --- | --- |
| New backend | `app/schemas/compatibility.py`, `app/models/compatibility.py`, `app/services/compatibility_engine.py`, `compatibility_service.py`, `compatibility_reports.py`, `app/api/compatibility_routes.py` |
| Migration / registration | New `backend/alembic/versions/0004_compatibility.py`; updated `backend/alembic/env.py`, `backend/app/main.py`, `backend/app/schemas/api.py` |
| Backend tests | New `test_compatibility_engine.py`, `test_compatibility_api.py`; extended `test_migrations.py` |
| New frontend | `src/pages/Compatibility.tsx`, `src/components/compatibility/{PolicyEditor,Findings}.tsx`, `src/types/compatibility.ts`, `src/services/compatibilityApi.ts`, `src/tests/compatibility.test.tsx`, `e2e/compatibility.spec.ts` |
| Frontend integration | Updated `src/App.tsx`, `src/pages/Comparisons.tsx`, `src/pages/ComparisonDetails.tsx`, `src/styles.css`, `package.json`, `package-lock.json` (application version 0.4.0; no dependency additions) |
| Fixtures and docs | Updated `sample-api/main.py`; new `examples/compatibility-policies.json`, `scripts/compatibility_smoke_test.py`; updated README, this guide, security and verification docs; archived Phase 3 verification; new Phase 5 roadmap |

## Verification and limits

See [`VERIFICATION.md`](VERIFICATION.md) for actual test counts and observed results. Backend tests exercise rule triggers/non-triggers, severity/confidence, masking, ignored-field precedence, ordered/unordered arrays, validation, deterministic results, source integrity, missing evidence, history, pagination and bounded/redacted/escaped reports. Integration tests cover record → replay → compare → analyze → policy edit → reanalysis → history → export. Migration checks preserve populated Phase 1–3 data. UI interaction tests cover overview, filters, evidence links, policy errors/saving, explicit reanalysis, history, downloads and empty/error states.

Docker Compose startup and real browser rendering are **unverified in the build environment**: Docker is unavailable and Chromium is blocked by a system socket restriction. Compose is statically checked; all services were exercised natively with PostgreSQL and real HTTP through Vite. A Playwright test for Phase 4 is included for a machine with a working browser. These limitations are not reported as passing acceptance checks.

This remains a local, trusted, single-user tool. It cannot discover actual consumer contracts, validate full OpenAPI/JSON Schema, infer semantic meanings of arbitrary values, recover redacted evidence, prove unrecorded behavior, or predict outages. Existing capture and synchronous replay limits remain. No LLM, authentication, production changes, deployments, schedules, collaborative features, or CI gates were added. See [`PHASE5.md`](PHASE5.md) for a proposed next phase.

# Phase 5 release audit

Audited 19 November 2026 against the actual Phase 4 source. This release focuses on integration and correctness, not the earlier speculative CI/suite roadmap.

| Priority | Finding | Implemented resolution |
| --- | --- | --- |
| P1 workflow | Replay requires separate navigation and explicit comparison before useful compatibility/report output; analyzing too early produces only missing-evidence results. | Added one explicit saved-evidence action that compares then analyzes without another outbound request. Keep existing granular APIs. |
| P1 data context | Recording detail does not synchronize its owning project; switching directly between replay detail IDs can briefly retain old session data. | Synchronized/reset detail state and retain project-aware navigation. |
| P1 execution controls | Exact origin/IP pinning, redirects disabled, deadlines, concurrency and batch limits exist; no shared time-window execution rate cap. | Added a bounded process-local execution rate limiter shared by direct captures and replay; preserve explicit local-block outcomes. |
| P2 performance | Recording summary queries load large request/response JSON that is never returned. | Selected only summary columns; added server-side literal search and method filters with pagination. |
| P2 performance | Compatibility history resolves project policies/rules repeatedly for every run; exact-run integrity checks load full source bodies/differences. | Shared settings load once and source IDs are validated with bounded relational queries. Final SELECT counts: 8 for two runs and 8 for ten, previously 12/44. |
| P2 UX | Reports are available only inside a selected compatibility run. | Added a Reports navigation entry using the existing compatibility history/detail implementation. |
| P2 UX | Request JSON validation appears only on send; request writes lack the explicit confirmation already used for replay. | Added immediate JSON validation, formatting, an explicit write confirmation and clear busy state. |
| P2 configuration | Health metadata still says Phase 3; sample-project creation assumes Docker even in native mode. | Corrected release metadata and added configured sample targets via a safe runtime configuration response. |
| P3 polish/docs | Phase labels dominate product navigation; Phase 5 currently describes an unimplemented CI proposal; no final demo/resume/interview report. | Released version 1.0.0, consistent product labels/focus/reduced-motion states, concise README architecture/demo and final evidence-based report. |

Existing controls inspected: structured input validation; SQLAlchemy parameterization; project/source relationship checks; immutable recording payloads; temporary replay override redaction; connection-time DNS validation and IP pinning with original Host/SNI; no redirect following; request/response/JSON limits; restrictive CORS/Host checks; HTML escaping/CSP and bounded reports; loopback Compose ports; migrations and startup replay recovery.

Existing features inspected: project/request/recording routes; replay models/service/override rules; recursive comparison and stored differences; compatibility policies/classifier/findings/history/report routes; all frontend workspaces; Alembic migrations 0001–0004; Compose/Dockerfiles/env examples; tests and docs. No remote repository or Git metadata is attached. No license choice is present.

The prompt's example internal URLs (`sample-api-v1:8000`, `sample-api-v2:8000`) do not match this established project. Preserve the working addresses `http://sample-api:8001` and `http://sample-api-v2:8001`; native targets use 127.0.0.1 ports 8001/8004. Document them consistently rather than invalidate existing project settings and recordings.

Docker is unavailable; fresh Chromium launch is blocked by process-singleton socket permission. Their acceptance checks remain open. Native live verification and automated tests passed; see [VERIFICATION.md](VERIFICATION.md). No public deployment is authorized or appropriate without additional access control and network isolation. Existing source is the release baseline; only task-owned build artifacts and caches are excluded from packaging.

## Release validation outcome

The six new backend cases and eight new DOM cases passed alongside the existing suites (209 backend / 27 UI total); TypeScript and production build passed. The real final demo yielded two explicit contract violations and retained the earlier assessment. PostgreSQL migration/persistence and backend restart checks passed. No schema redesign or large product module was introduced. The remaining Docker/browser/visual checks are identified as partial acceptance in [the completion report](PHASE5.md).

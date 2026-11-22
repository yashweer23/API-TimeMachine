# Recording and replay security design

## Trust boundary

This version is a loopback-bound, trusted-local-user application. There are no accounts or authorization rules. Database and sample services are development resources. The backend is not an unrestricted HTTP proxy: target configuration alone does not grant permission to reach a host.

## Destination checks

1. Validate scheme, hostname, port, and URL syntax. Reject embedded credentials, query strings, fragments, ambiguous backslashes, and invalid paths.
2. Compare the normalized origin with an exact operator-maintained allowlist. Scheme and port are part of the match; wildcards are not supported.
3. Resolve DNS with a bounded timeout. Validate **all** returned addresses, rejecting mixed safe/unsafe responses.
4. Reject non-global addresses unless both the exact development origin and its address range are explicitly configured. Link-local metadata, multicast, unspecified, and reserved addresses remain blocked even with a development exception.
5. Connect to a validated literal IP, preserving the original HTTP Host and TLS SNI hostname. Certificate verification remains enabled. This avoids the second DNS lookup that would otherwise permit a rebinding race.
6. Disable redirects and environment proxy discovery. A redirect response is saved without requesting its Location.

HTTPX documents the explicit-IP/SNI mechanism in its [request extensions documentation](https://www.python-httpx.org/advanced/extensions/#sni_hostname) and environment-proxy behavior in [environment variables](https://www.python-httpx.org/environment_variables/).

Transport-controlled headers cannot be overridden by the request editor: Host, content length, transfer encoding, connection, upgrade, proxy authorization, accept encoding, TE, trailer, and Expect are controlled or rejected. Values must be printable ASCII, and duplicate header names are rejected case-insensitively.

## Resource limits and failure semantics

- Incoming JSON is capped before parsing; only JSON writes are accepted.
- Configurable connection/read/total timeouts apply. The total deadline covers admission queue, DNS, connection, and body streaming.
- An application semaphore limits simultaneous outbound work in the single backend process.
- Responses are streamed with a byte cap. Oversized, compressed, binary, malformed, or incompatible bodies are omitted and flagged, retaining actual response status when available.
- Completed HTTP errors are not transport failures. A `404` capture remains a real `404` with its body.
- Failure records use stable codes and safe messages. Raw network exceptions, validation inputs, and SQL error details are not sent back or persisted. Uvicorn access logs are disabled in the supplied commands to reduce incidental request logging.

## Storage redaction

Headers, query values, and JSON objects/arrays are recursively sanitized before storage. Key normalization is case-insensitive and punctuation-insensitive. Default matches include authorization, cookies, password/passwd, secret, token, API key, credential, and private key. `REDACT_FIELDS` adds exact normalized keys.

Known sensitive outgoing values are tracked transiently and scrubbed from echoed strings. Sensitive values discovered in response JSON are also scrubbed from response headers and other response values. Text responses receive credential-pattern redaction. The stored value is `[REDACTED]`, preserving surrounding JSON structure and non-sensitive primitive types.

This is not a universal secret or PII detector. For ordinary recording, short secrets are scrubbed when a whole value matches; arbitrary substrings shorter than four characters are not globally replaced. Replay's explicit temporary values use stricter matching, including short substrings and numeric/boolean scalars, which can mask coincidentally matching data. Unknown secret names, secrets encoded differently by a target, URL path tokens, and domain-specific personal data require operator judgment and additional redaction fields. The UI never renders response HTML; JSON/text is displayed as escaped React text.

## Replay boundary

Replay reuses the same HTTP executor and revalidates DNS/IP policy for each call. Every selected recording must belong to the selected project; all effective requests are reconstructed and checked for masked placeholders before execution starts. Original request and response captures are never modified by replay.

POST, PUT, PATCH, and DELETE require explicit API confirmation and a UI confirmation dialog. No request is retried automatically. Temporary headers and explicit override values are collected before persistence; recognized echoes in headers, bodies, keys, and metadata are sanitized. Temporary drafts clear when execution starts. Validation errors omit input values and potentially secret-bearing dictionary keys. Supplied commands disable access logs; the application does not log payloads. Do not enable HTTP debug logging or request-body logging around authenticated replay.

Sessions have bounded batch size, network execution time, and admission capacity. Database work can add overhead to the execution budget. Pending rows and each settled result are committed separately. Single-process startup recovery records interrupted/unknown outcomes rather than resending writes. A target may have processed a request even if a client disconnects or the database fails before persistence.

## Deployment scope

This remains a trusted, local, single-user application. Project association checks are not user authorization. Multiple workers/replicas are unsupported because admission limits and startup recovery are process-local. Shared deployment would require authentication, authorization, coordinated job ownership, controlled egress, secrets management, and deployment-specific review; none is claimed in release 1.0.0.


## Comparison boundary

Comparison routes only read persisted original/replay snapshots; they never invoke the target API. They validate the recording/session project relationship and refuse pending/running results. This is relationship integrity, not user authorization.

Effective rules are validated exact JSON Pointers and header-name lists, with no evaluation or wildcard execution. Canonical hashes and an algorithm version deduplicate calculations; historical rows retain their effective rules. Changing defaults cannot overwrite old evidence.

Inputs, nesting, visited values, path length and generated difference count are bounded. Comparison runs in a request thread with no job queue. Large difference values are represented by short previews and source references, with complete sanitized values available on demand. Additional redaction precedes comparison/value retrieval; matching redaction markers do not prove equivalence. Masked, failed, unsupported or limited inputs have explicit incomplete/unavailable states.

Repeated response headers are preserved for new captures; legacy flattened values remain opaque. Sensitive cookie/authentication data remains sanitized regardless of whether its header is ignored. Browser copy operations copy only the displayed stored/sanitized data.

## Phase 4 compatibility and exports

Compatibility assessment reads finalized saved comparisons and sanitized snapshots; it never sends API requests. Endpoint contracts use validated exact method/path keys, bounded JSON Pointers and enumerated field types. No expression evaluator, LLM or remote schema loader is involved. Policies are project-scoped; source/session/project relationships are checked when assessing and resolving exact analyses/runs. Historical policies are stored with the result, not resolved from mutable current settings at export time.

Report content is allowlisted and bounded, with no raw request credentials, temporary overrides, environment configuration or complete response bodies. Source/target URLs omit user-info/query/fragment. The existing key/pattern redactor sanitizes evidence and exports. Dynamic HTML is escaped, no external resources or scripts are loaded, and CSP/attachment/nosniff headers are set. Filename content is a validated UUID. JSON is limited to 2 MB, HTML to 4 MB, and exports state when the 500-finding cap omits entries. Finding search escapes SQL wildcard characters. These controls do not infer arbitrary secrets in names/paths or replace the existing trusted-local deployment boundary.

Redacted ancestor values cannot establish child absence or original type. Incomplete, masked, ignored, limited and missing evidence stays explicitly unassessed; an absence of detected changes is not a universal guarantee. Analysis runs are immutable and deduplicated by persisted evidence, engine and effective policy. The no-additional-fields policy is a comparison against the recorded baseline, not general JSON Schema validation.

## Phase 5 integration controls

Direct capture and replay share a rolling 60-second execution admission limit (default 120) plus the existing concurrent-request bound. Admissions count attempts, including attempts that later fail validation/transport or wait in the queue. The counter stores at most the configured maximum timestamps and uses a lock and monotonic clock. A denied execution sends no target request and persists `execution_rate_limited` with null HTTP status; replay classifies it as blocked. This is a per-process development guard, not distributed abuse protection; restarting resets it.

The request-builder UI now confirms non-GET methods before sending and rejects malformed/nonfinite/unsafe-integer JSON before browser serialization. Direct APIs still execute an explicitly submitted valid send request. Existing API confirmation remains required for replay writes. Cancelling the UI dialog produces no send call.

The safe `/api/config` response exposes only allowed sample defaults, the rate setting, local deployment mode and release version; no database connection or credential settings. The sample defaults do not grant new target permissions. Recording search uses escaped SQL wildcard literals and bound query parameters. List queries avoid loading request/response payloads. History and exact report reads retain relational source-project checks without loading full source bodies.

`/replay-sessions/{id}/assess` performs comparison then assessment using saved data, rejects running sessions and reuses the established validation/redaction/rule/policy paths. It never executes target HTTP. Download errors are shown in the interface; a failed export is not mislabeled as a successful file.

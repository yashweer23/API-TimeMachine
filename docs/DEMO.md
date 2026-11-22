# A three-to-five-minute demonstration

Use the bundled deterministic sample APIs. No paid or third-party service is needed. The flow below creates actual captures and reports, not precomputed engine output.

## Start

From the extracted `api-timemachine` folder:

```sh
docker compose up --build
```

Open http://localhost:5175. Docker startup remains a local acceptance check; the same workflow was verified using native sample servers, FastAPI, Vite and PostgreSQL. Native setup is in [SETUP.md](SETUP.md).

| Target | Docker backend address | Native backend address |
| --- | --- | --- |
| Sample v1 | `http://sample-api:8001` | `http://127.0.0.1:8001` |
| Sample v2 | `http://sample-api-v2:8001` | `http://127.0.0.1:8004` |

Do not use the host's v1 Docker port `8003` as an internal backend target.

## Walkthrough

| Time | Action | What to explain |
| --- | --- | --- |
| 0:00–0:35 | Click **New project**; name it **Sample API Regression Testing**, target v1, and create. | Projects scope the baseline, replay evidence and policy. |
| 0:35–1:10 | Set `GET /users/1`; use **Details** to name it **User v1 baseline**. Click **Send request**, inspect status/body/duration, then **Mark baseline**. | The saved response is real, sanitized and durable. |
| 1:10–1:50 | Open **Replay**, select that baseline, choose v2, name the session **Sample user v1 to v2**, and click **Run replay**. | The new response is stored separately. Show the original/replayed panels. |
| 1:50–2:30 | Click **Compare & analyze**; expand a finding and follow its exact difference link. | Missing `name`, added `full_name`, changed `id` type and changed values are observed evidence. No new target call is made during comparison. |
| 2:30–3:30 | Return to Compatibility, expand **Endpoint compatibility policies**, paste the policy below and save; click **Compare & analyze**. | Two explicit contract violations now support an incompatible verdict. Earlier results retain their earlier policy. |
| 3:30–4:30 | Download JSON and HTML. Open **Reports**, select this session's earlier/current runs, and refresh the selected page. | Counts and evidence come from stored analyses. Historical runs remain available; reports are portable. |

Apply this project policy:

```json
{
  "endpoints": [
    {
      "method": "GET",
      "endpoint_path": "/users/1",
      "expected_status_codes": [200],
      "required_json_paths": ["/data/id", "/data/name"],
      "expected_types": {"/data/id": "integer"},
      "allowed_content_types": ["application/json"],
      "allow_additional_fields": true,
      "dynamic_json_paths": ["/version"]
    }
  ]
}
```

Expected results: before policy, **0 confirmed** findings; after policy, **2 confirmed** findings and `incompatible_with_configured_contract`. The removed required name and integer-to-string ID change are confirmed; an added allowed field is not automatically breaking. These results were checked over real HTTP and PostgreSQL. Confirmed findings establish configured-contract violations, not proof that every consumer fails.

## Optional preparation script

With the application running, from the project root:

```sh
python scripts/release_demo.py --backend http://127.0.0.1:5175 --report-dir demo-output
```

The script reads the allowed sample URLs from `/api/config`. Native `.env` defaults are supported. You may explicitly supply `--v1 http://127.0.0.1:8001 --v2 http://127.0.0.1:8004` when those addresses are allowed. Only standard-library Python is required.

Each run creates one new demonstration project; it does not reset or delete other data. It sends only GET to the target, persists the baseline/replay, computes both policy states, checks idempotence and immutable evidence, downloads actual JSON/HTML and prints exact replay/report links. Optional files go under the specified local directory; `demo-output/` is ignored by Git.

## Extra examples if time permits

- `/regression/timestamp`: ignore `/generated_at`, recompute and compare the new result with its retained predecessor.
- `/users/999`: a real HTTP 404 remains distinct from a connection error.
- `/redirect`: capture HTTP 302 without following it.
- `/slow`: show a timeout with a null response status rather than an invented HTTP 500.
- `POST /echo`: review the UI confirmation before executing; use only harmless sample data. This is optional and not required by the GET-only release demo.

[README](../README.md) · [Verification](VERIFICATION.md)

import { useState } from "react";
import type { PolicyBundle, PolicySettings } from "../../types/compatibility";
import { compatibilityApi } from "../../services/compatibilityApi";
import { errorMessage } from "../../services/api";
export function PolicyEditor({
  settings,
  onSaved,
}: {
  settings: PolicySettings;
  onSaved: (value: PolicySettings) => void;
}) {
  const [draft, setDraft] = useState(
      JSON.stringify(settings.policies, null, 2),
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false);
  const save = async () => {
    setError("");
    setSaved(false);
    let parsed: PolicyBundle;
    try {
      parsed = JSON.parse(draft) as PolicyBundle;
      if (!parsed || !Array.isArray(parsed.endpoints))
        throw new Error("Use a JSON object with an endpoints array.");
    } catch (e) {
      setError(`Invalid policy JSON. ${errorMessage(e)}`);
      return;
    }
    setBusy(true);
    try {
      const result = await compatibilityApi.savePolicies(
        settings.project_id,
        parsed,
      );
      setDraft(JSON.stringify(result.policies, null, 2));
      setSaved(true);
      onSaved(result);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="panel compatibility-policies">
      <summary>
        Endpoint compatibility policies{" "}
        <span>{settings.policies.endpoints.length} configured</span>
      </summary>
      <p>
        Declare only requirements that consumers actually depend on. Policies
        match an HTTP method and an exact recorded path. Saving does not
        reanalyze existing results.
      </p>
      <div className="policy-guide">
        <div>
          <strong>Contract checks</strong>
          <p>
            Successful status codes (200–299), required JSON paths, field types,
            required header names, and allowed media types. Empty lists impose
            no constraint.
          </p>
        </div>
        <div>
          <strong>Explicit permissions</strong>
          <p>
            Dynamic paths permit value changes, while types and presence remain
            checked. Additional fields: <code>true</code> permits new object
            properties; <code>false</code> prohibits additions relative to the
            baseline; <code>null</code> uses defaults.
          </p>
        </div>
      </div>
      <label htmlFor="compatibility-policy-json">Policies JSON</label>
      <textarea
        id="compatibility-policy-json"
        className="policy-json"
        spellCheck={false}
        rows={18}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          setSaved(false);
        }}
      />
      <p className="muted">
        JSON Pointer examples: <code>/user/id</code>, <code>/items/0/name</code>
        ; <code>""</code> means the root. No wildcards or expressions. Types:
        object, array, string, number, integer, boolean, null. At most 50
        endpoints.
      </p>
      <details className="policy-example">
        <summary>Show policy example</summary>
        <pre>
          {JSON.stringify(
            {
              endpoints: [
                {
                  method: "GET",
                  endpoint_path: "/users/1",
                  expected_status_codes: [200],
                  required_json_paths: ["/id"],
                  expected_types: { "/id": "integer" },
                  required_headers: ["content-type"],
                  allowed_content_types: ["application/json"],
                  allow_additional_fields: true,
                  dynamic_json_paths: ["/updated_at"],
                },
              ],
            },
            null,
            2,
          )}
        </pre>
      </details>
      {error && (
        <div role="alert" className="error-box">
          {error}
        </div>
      )}
      <button
        className="button primary"
        disabled={busy}
        onClick={() => void save()}
      >
        {busy ? "Saving policies…" : "Save policies"}
      </button>
      {saved && (
        <p role="status">
          Policies saved. Select Analyze session to assess with these
          requirements. Historical results are preserved.
        </p>
      )}
    </details>
  );
}

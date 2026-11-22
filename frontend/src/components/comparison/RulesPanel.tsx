import { useState } from "react";
import type { ComparisonRules, RulesSettings } from "../../types/comparison";
import { comparisonApi } from "../../services/comparisonApi";
import { errorMessage } from "../../services/api";
export function RulesPanel({
  settings,
  onSaved,
}: {
  settings: RulesSettings;
  onSaved: (s: RulesSettings) => void;
}) {
  const [paths, setPaths] = useState(
    settings.rules.ignored_json_paths
      .map((p) => (p === "" ? "(root)" : p))
      .join("\n"),
  );
  const [headers, setHeaders] = useState(
    settings.rules.ignored_headers.join("\n"),
  );
  const [arrays, setArrays] = useState(
    settings.rules.unordered_array_paths
      .map((p) => (p === "" ? "(root)" : p))
      .join("\n"),
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false);
  const lines = (value: string) =>
    value
      .split("\n")
      .filter((v) => v !== "")
      .map((v) => (v === "(root)" ? "" : v));
  const save = async () => {
    setError("");
    setSaved(false);
    const rules: ComparisonRules = {
      ignored_json_paths: lines(paths),
      ignored_headers: headers
        .split("\n")
        .map((v) => v.trim())
        .filter(Boolean),
      unordered_array_paths: lines(arrays),
    };
    try {
      for (const path of [
        ...rules.ignored_json_paths,
        ...rules.unordered_array_paths,
      ])
        if (path !== "" && (!path.startsWith("/") || /~(?![01])/.test(path)))
          throw new Error(
            "Use JSON Pointer paths such as /profile/city. Escape / as ~1 and ~ as ~0.",
          );
      if (
        rules.ignored_json_paths.length > 50 ||
        rules.ignored_headers.length > 50 ||
        rules.unordered_array_paths.length > 20
      )
        throw new Error(
          "Use at most 50 ignored paths, 50 headers, and 20 unordered arrays.",
        );
      for (const path of rules.unordered_array_paths)
        if (
          [...rules.ignored_json_paths, ...rules.unordered_array_paths].some(
            (p) => p.startsWith(path + "/"),
          )
        )
          throw new Error(
            "Rules inside unordered arrays are ambiguous. Use the whole array path.",
          );
      if (
        rules.ignored_headers.some(
          (h) => !/^[-!#$%&'*+.^_`|~0-9A-Za-z]+$/.test(h),
        )
      )
        throw new Error("Enter valid HTTP header names, one per line.");
      setBusy(true);
      const result = await comparisonApi.saveSettings(
        settings.project_id,
        rules,
      );
      onSaved(result);
      setSaved(true);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="panel comparison-rules">
      <summary>
        Comparison rules <span>Project defaults · exact paths</span>
      </summary>
      <div className="rules-content">
        <p>
          One entry per line. Paths are exact JSON Pointers:{" "}
          <code>/profile/city</code>, <code>/roles/0</code>. Use <code>~1</code>{" "}
          for a slash, <code>~0</code> for a tilde, and <code>(root)</code> for
          the entire body.
        </p>
        <div className="rules-grid">
          <label>
            Ignored JSON paths
            <textarea
              aria-label="Ignored JSON paths"
              value={paths}
              onChange={(e) => {
                setPaths(e.target.value);
                setSaved(false);
              }}
              placeholder="/generated_at"
              spellCheck={false}
            />
          </label>
          <label>
            Ignored response headers
            <textarea
              aria-label="Ignored response headers"
              value={headers}
              onChange={(e) => {
                setHeaders(e.target.value);
                setSaved(false);
              }}
              spellCheck={false}
            />
          </label>
          <label>
            Unordered array paths
            <textarea
              aria-label="Unordered array paths"
              value={arrays}
              onChange={(e) => {
                setArrays(e.target.value);
                setSaved(false);
              }}
              placeholder="/roles"
              spellCheck={false}
            />
          </label>
        </div>
        <p>
          Arrays use indexes by default. Unordered arrays use exact multiset
          equality; a changed multiset produces one array change. Saving rules
          preserves historical results. Recalculate explicitly to use these
          settings.
        </p>
        {error && (
          <div role="alert" className="error-box">
            {error}
          </div>
        )}
        {saved && <p role="status">Rules saved. Recalculate to apply them.</p>}
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => void save()}
        >
          {busy ? "Saving…" : "Save comparison rules"}
        </button>
      </div>
    </details>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { compatibilityApi } from "../../services/compatibilityApi";
import { errorMessage } from "../../services/api";
import { classLabels, type FindingsPage } from "../../types/compatibility";
export function Findings({ runId }: { runId: string }) {
  const [classification, setClassification] = useState(""),
    [severity, setSeverity] = useState(""),
    [method, setMethod] = useState(""),
    [endpoint, setEndpoint] = useState(""),
    [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0),
    [data, setData] = useState<FindingsPage | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [revision, setRevision] = useState(0);
  const settledEndpoint = useDebouncedValue(endpoint),
    settledSearch = useDebouncedValue(search);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    setData(null);
    const params = new URLSearchParams({ limit: "25", offset: String(offset) });
    Object.entries({
      classification,
      severity,
      method,
      endpoint: settledEndpoint,
      search: settledSearch,
    }).forEach(([k, v]) => {
      if (v) params.set(k, v);
    });
    compatibilityApi
      .findings(runId, params)
      .then((v) => {
        if (live) setData(v);
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [
    runId,
    classification,
    severity,
    method,
    settledEndpoint,
    settledSearch,
    offset,
    revision,
  ]);
  const filter = (set: (value: string) => void, value: string) => {
    set(value);
    setOffset(0);
  };
  return (
    <section
      aria-label="Compatibility findings"
      className="compatibility-findings"
    >
      <div className="section-heading">
        <h2>Evidence and findings</h2>
        <span>{data?.total ?? "…"} matching findings</span>
      </div>
      <div className="finding-filters">
        <label>
          Classification
          <select
            value={classification}
            onChange={(e) => filter(setClassification, e.target.value)}
          >
            <option value="">All classifications</option>
            {Object.entries(classLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Severity
          <select
            value={severity}
            onChange={(e) => filter(setSeverity, e.target.value)}
          >
            <option value="">All severities</option>
            {["critical", "high", "medium", "low", "unrated"].map((v) => (
              <option value={v} key={v}>
                {v === "unrated" ? "Not rated" : v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Method
          <select
            value={method}
            onChange={(e) => filter(setMethod, e.target.value)}
          >
            <option value="">All methods</option>
            {["GET", "POST", "PUT", "PATCH", "DELETE"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Endpoint contains
          <input
            value={endpoint}
            onChange={(e) => filter(setEndpoint, e.target.value)}
            placeholder="/users"
            maxLength={2048}
          />
        </label>
        <label>
          Search path or title
          <input
            value={search}
            onChange={(e) => filter(setSearch, e.target.value)}
            placeholder="/id or required"
            maxLength={200}
          />
        </label>
      </div>
      {error && (
        <div role="alert" className="error-box">
          {error}
          <button
            className="text-button"
            onClick={() => setRevision((v) => v + 1)}
          >
            Retry findings
          </button>
        </div>
      )}
      {loading && <p role="status">Loading findings…</p>}
      {!loading && data?.total === 0 && (
        <div className="empty-state">
          <h3>No matching findings</h3>
          <p>
            Try another filter. A zero finding count does not override the
            session’s evidence coverage.
          </p>
        </div>
      )}
      {data?.items.map((f) => (
        <details
          className={`panel finding-card finding-${f.classification}`}
          key={f.id}
        >
          <summary>
            <div>
              <span className="finding-label">
                {classLabels[f.classification]}
              </span>
              <h3>{f.title}</h3>
              <code>
                {f.request_method} {f.endpoint_path} · {f.path || "(root)"}
              </code>
            </div>
            <div className="finding-rating">
              <span>{f.severity || "Not rated"}</span>
              <small>{f.confidence} confidence</small>
            </div>
          </summary>
          <div className="finding-content">
            <p>{f.explanation}</p>
            <p>
              <strong>Recommended action:</strong> {f.recommended_action}
            </p>
            <div className="evidence-pair">
              {(["old", "new"] as const).map((side) => (
                <div key={side}>
                  <h4>{side === "old" ? "Recorded" : "Replayed"}</h4>
                  <pre>{f.evidence[`${side}_preview`] ?? "Not available"}</pre>
                  {f.evidence[`${side}_value_truncated`] && (
                    <small>
                      Preview truncated. Inspect the saved Phase 3 difference
                      for full evidence.
                    </small>
                  )}
                </div>
              ))}
            </div>
            <dl className="finding-facts">
              <dt>Detected change</dt>
              <dd>{f.change_type.replaceAll("_", " ")}</dd>
              <dt>Rule</dt>
              <dd>
                <code>{f.rule_id}</code>
              </dd>
              <dt>Explicit requirement</dt>
              <dd>
                <code>
                  {f.evidence.requirement == null
                    ? "None supplied for this finding"
                    : JSON.stringify(f.evidence.requirement)}
                </code>
              </dd>
            </dl>
            <Link
              className="text-button"
              to={`/comparisons/${f.comparison_id}${f.difference_id ? `?difference=${f.difference_id}` : ""}`}
            >
              Open saved Phase 3 {f.difference_id ? "difference" : "comparison"}
            </Link>
            {!f.difference_id && (
              <p className="muted">
                This is a direct contract or evidence-coverage check; it may not
                have an individual Phase 3 difference.
              </p>
            )}
          </div>
        </details>
      ))}
      <div className="pagination">
        <span>
          Showing {data?.items.length ?? 0} of {data?.total ?? 0}
        </span>
        <div>
          <button
            disabled={!offset || loading}
            onClick={() => setOffset((v) => Math.max(0, v - 25))}
            aria-label="Previous findings"
          >
            Previous
          </button>
          <button
            disabled={loading || offset + 25 >= (data?.total ?? 0)}
            onClick={() => setOffset((v) => v + 25)}
            aria-label="Next findings"
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}

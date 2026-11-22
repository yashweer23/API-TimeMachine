import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GitCompareArrows, ChevronLeft, ChevronRight } from "lucide-react";
import type { Project } from "../types";
import type { ReplaySessionPage } from "../types/replay";
import type {
  ComparisonPage,
  RulesSettings,
  SessionComparisons,
} from "../types/comparison";
import { comparisonApi } from "../services/comparisonApi";
import { replayApi } from "../services/replayApi";
import { errorMessage } from "../services/api";
import { RulesPanel } from "../components/comparison/RulesPanel";
export function Comparisons({ project }: { project: Project }) {
  const [params, setParams] = useSearchParams(),
    sessionId = params.get("session") || "";
  const [sessions, setSessions] = useState<ReplaySessionPage | null>(null),
    [sessionOffset, setSessionOffset] = useState(0),
    [settings, setSettings] = useState<RulesSettings | null>(null),
    [history, setHistory] = useState<ComparisonPage | null>(null),
    [offset, setOffset] = useState(0),
    [overview, setOverview] = useState<SessionComparisons | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    Promise.all([
      replayApi.sessions(project.id, sessionOffset),
      comparisonApi.settings(project.id),
      comparisonApi.history(project.id, offset),
    ])
      .then(([runs, rules, past]) => {
        if (live) {
          setSessions(runs);
          setSettings(rules);
          setHistory(past);
          setError("");
        }
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
  }, [project.id, sessionOffset, offset, revision]);
  useEffect(() => {
    setOverview(null);
    if (!sessionId) return;
    let live = true;
    comparisonApi
      .session(sessionId)
      .then((s) => {
        if (live) {
          if (s.project_id !== project.id)
            throw new Error("Choose the project that owns this session.");
          setOverview(s);
        }
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [sessionId, project.id, revision]);
  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await comparisonApi.compareSession(sessionId);
      setOverview(data);
      setRevision((v) => v + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="page-intro">
        <div>
          <h1>Comparisons</h1>
          <p>See exactly what changed in your saved responses.</p>
        </div>
        <Link to="/replay/history" className="button secondary">
          Replay history
        </Link>
      </div>
      {error && (
        <div className="error-box mb-5" role="alert">
          {error}
          <button
            className="text-button"
            onClick={() => setRevision((v) => v + 1)}
          >
            Retry
          </button>
        </div>
      )}
      {loading && !settings ? (
        <div className="empty-state" role="status">
          Loading comparisons…
        </div>
      ) : (
        <>
          <section className="panel comparison-launch">
            <div>
              <h2>Compare a replay session</h2>
              <p>
                Uses saved snapshots. Comparing never sends an API request to
                the target.
              </p>
            </div>
            <div className="comparison-launch-fields">
              <label>
                Replay session
                <select
                  aria-label="Session to compare"
                  value={sessionId}
                  onChange={(e) =>
                    setParams(e.target.value ? { session: e.target.value } : {})
                  }
                >
                  <option value="">Choose a session</option>
                  {sessionId &&
                    !sessions?.items.some((s) => s.id === sessionId) && (
                      <option value={sessionId}>
                        {overview?.session_name || "Selected session"}
                      </option>
                    )}
                  {sessions?.items.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} · {new Date(s.started_at).toLocaleString()} ·{" "}
                      {s.total_requests} requests
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="button primary"
                disabled={!sessionId || !overview || busy}
                onClick={() => void run()}
              >
                <GitCompareArrows size={15} />
                {busy ? "Comparing saved responses…" : "Compare session"}
              </button>
            </div>
            <div className="pagination">
              <span>{sessions?.total ?? 0} replay sessions</span>
              <div>
                <button
                  aria-label="Previous replay session choices"
                  disabled={!sessionOffset}
                  onClick={() => setSessionOffset((v) => Math.max(0, v - 20))}
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  aria-label="Next replay session choices"
                  disabled={sessionOffset + 20 >= (sessions?.total ?? 0)}
                  onClick={() => setSessionOffset((v) => v + 20)}
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </section>
          {busy && (
            <p role="status" className="comparison-progress">
              Comparing and saving results. Existing comparisons with matching
              settings are reused.
            </p>
          )}
          {overview && (
            <section aria-label="Session comparison overview">
              <Link
                className="button secondary mb-4"
                to={`/compatibility?project=${project.id}&session=${sessionId}`}
              >
                Assess compatibility
              </Link>
              <div className="comparison-stat-grid">
                {[
                  ["Compared", overview.totals.compared],
                  ["Identical", overview.totals.identical],
                  ["With differences", overview.totals.different],
                  ["Incomplete / unavailable", overview.totals.incomparable],
                  ["Detected differences", overview.totals.differences],
                ].map(([label, value]) => (
                  <div className="panel comparison-stat" key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <div className="comparison-counts">
                {[
                  ["Added", "field_added"],
                  ["Removed", "field_removed"],
                  ["Values", "value_changed"],
                  ["Types", "type_changed"],
                  ["Statuses", "status_changed"],
                  ["Headers", "headers"],
                ].map(([label, key]) => (
                  <span key={key}>
                    {label}{" "}
                    <strong>
                      {key === "headers"
                        ? overview.totals.header_added +
                          overview.totals.header_removed +
                          overview.totals.header_changed
                        : overview.totals[key]}
                    </strong>
                  </span>
                ))}
              </div>
              {overview.pending_requests > 0 && (
                <p className="warning-note">
                  {overview.pending_requests} requests are still pending/running
                  and are excluded until finalized.
                </p>
              )}
              {!overview.items.length ? (
                <div className="empty-state">
                  <h3>No comparisons for this session yet</h3>
                  <p>
                    Select Compare session to analyze its finalized results.
                  </p>
                </div>
              ) : (
                <div className="panel table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>REQUEST</th>
                        <th>COMPARISON</th>
                        <th>DIFFERENCES</th>
                        <th>RULES</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.items.map((c) => (
                        <tr key={c.id}>
                          <td>
                            <Link
                              className="history-session"
                              to={`/comparisons/${c.id}`}
                            >
                              <strong>
                                {c.request_method} {c.endpoint_path}
                              </strong>
                              <small>{c.recording_name}</small>
                            </Link>
                          </td>
                          <td>
                            <span
                              className={`comparison-status state-${c.comparison_status}`}
                            >
                              {c.comparison_status}
                            </span>
                          </td>
                          <td>{c.total_differences}</td>
                          <td>{c.is_current ? "Current" : "Older settings"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
          {settings && (
            <RulesPanel
              key={settings.rules_hash}
              settings={settings}
              onSaved={(s) => {
                setSettings(s);
                setRevision((v) => v + 1);
              }}
            />
          )}
          <section
            className="panel comparison-history"
            aria-label="Comparison history"
          >
            <div className="section-heading">
              <h2>Comparison history</h2>
              <span>Every saved rule configuration</span>
            </div>
            {!history?.items.length ? (
              <div className="empty-state">
                <h3>No saved comparisons</h3>
                <p>Replay a recording, then compare its saved responses.</p>
              </div>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>ORIGINAL / SESSION</th>
                      <th>COMPARED</th>
                      <th>RESULT</th>
                      <th>DIFFERENCES</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.items.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link
                            className="history-session"
                            to={`/comparisons/${c.id}`}
                          >
                            <strong>{c.recording_name}</strong>
                            <small>
                              {c.session_name}
                              {!c.is_current ? " · Older settings" : ""}
                            </small>
                          </Link>
                        </td>
                        <td>{new Date(c.compared_at).toLocaleString()}</td>
                        <td>
                          <span
                            className={`comparison-status state-${c.comparison_status}`}
                          >
                            {c.comparison_status}
                          </span>
                        </td>
                        <td>{c.total_differences}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="pagination">
              <span>{history?.total ?? 0} saved comparisons</span>
              <div>
                <button
                  aria-label="Previous comparisons"
                  disabled={!offset || loading}
                  onClick={() => setOffset((v) => Math.max(0, v - 20))}
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  aria-label="Next comparisons"
                  disabled={loading || offset + 20 >= (history?.total ?? 0)}
                  onClick={() => setOffset((v) => v + 20)}
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}

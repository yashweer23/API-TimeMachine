import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import type { Project } from "../types";
import type { ReplaySessionPage } from "../types/replay";
import {
  verdictLabels,
  type CompatibilityHistory,
  type CompatibilityRun,
  type PolicySettings,
} from "../types/compatibility";
import { compatibilityApi } from "../services/compatibilityApi";
import { replayApi } from "../services/replayApi";
import { errorMessage } from "../services/api";
import { PolicyEditor } from "../components/compatibility/PolicyEditor";
import { ReportDownloads } from "../components/compatibility/ReportDownloads";
import { Findings } from "../components/compatibility/Findings";
export function Compatibility({
  project,
  reportsOnly = false,
}: {
  project: Project;
  reportsOnly?: boolean;
}) {
  const [params, setParams] = useSearchParams(),
    sessionId = params.get("session") || "",
    runId = params.get("run") || "";
  const [sessions, setSessions] = useState<ReplaySessionPage | null>(null),
    [sessionOffset, setSessionOffset] = useState(0),
    [settings, setSettings] = useState<PolicySettings | null>(null),
    [history, setHistory] = useState<CompatibilityHistory | null>(null),
    [offset, setOffset] = useState(0),
    [run, setRun] = useState<CompatibilityRun | null>(null),
    [error, setError] = useState(""),
    [runError, setRunError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    Promise.all([
      replayApi.sessions(project.id, sessionOffset),
      compatibilityApi.policies(project.id),
      compatibilityApi.history(project.id, offset),
    ])
      .then(([s, p, h]) => {
        if (live) {
          setSessions(s);
          setSettings(p);
          setHistory(h);
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
    let live = true;
    setRun(null);
    setRunError("");
    if (runId)
      compatibilityApi
        .run(runId)
        .then((r) => {
          if (live) {
            if (r.project_id !== project.id)
              throw new Error("Select the project that owns this analysis.");
            setRun(r);
          }
        })
        .catch((e) => {
          if (live) setRunError(errorMessage(e));
        });
    return () => {
      live = false;
    };
  }, [runId, project.id, revision]);
  const analyze = async (compareFirst = false) => {
    setBusy(true);
    setError("");
    try {
      const r = await (
        compareFirst ? compatibilityApi.assess : compatibilityApi.analyze
      )(sessionId || run!.replay_session_id);
      setRun(r);
      setParams({
        project: project.id,
        session: r.replay_session_id,
        run: r.id,
      });
      setRevision((v) => v + 1);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const openRun = (r: CompatibilityRun) =>
    `${reportsOnly ? "/reports" : "/compatibility"}?project=${project.id}&session=${r.replay_session_id}&run=${r.id}`;
  return (
    <>
      <div className="page-intro">
        <div>
          <h1>{reportsOnly ? "Reports" : "Compatibility"}</h1>
          <p>
            {reportsOnly
              ? "Open a saved analysis and download its reproducible report."
              : "Assess saved responses against your endpoint policies."}
          </p>
        </div>
        <Link
          className="button secondary"
          to={`/comparisons?project=${project.id}${sessionId ? "&session=" + sessionId : ""}`}
        >
          Open comparisons
        </Link>
      </div>
      {(error || runError) && (
        <div className="error-box mb-5" role="alert">
          {error || runError}
          <button
            className="text-button"
            onClick={() => setRevision((v) => v + 1)}
          >
            Retry
          </button>
        </div>
      )}
      {loading && !settings ? (
        <p role="status">Loading compatibility workspace…</p>
      ) : (
        <>
          {!reportsOnly && (
            <section className="panel comparison-launch">
              <div>
                <h2>Analyze saved comparisons</h2>
                <p>
                  Uses saved evidence and explicit policies. Analysis does not
                  send requests to your API.
                </p>
              </div>
              <div className="comparison-launch-fields">
                <label>
                  Replay session
                  <select
                    aria-label="Session to analyze"
                    value={sessionId}
                    onChange={(e) => {
                      setError("");
                      setParams(
                        e.target.value
                          ? { project: project.id, session: e.target.value }
                          : { project: project.id },
                      );
                    }}
                  >
                    <option value="">Choose a session</option>
                    {sessionId &&
                      !sessions?.items.some((s) => s.id === sessionId) && (
                        <option value={sessionId}>
                          {run?.metadata_snapshot.session_name ||
                            "Selected session"}
                        </option>
                      )}
                    {sessions?.items.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} · {s.status} · {s.total_requests} requests
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="button primary"
                  disabled={busy || (!sessionId && !run)}
                  onClick={() => void analyze(true)}
                >
                  Compare &amp; analyze
                </button>
                <button
                  className="button secondary"
                  onClick={() => void analyze()}
                  disabled={busy || (!sessionId && !run)}
                >
                  <ShieldCheck size={16} />
                  {busy ? "Analyzing evidence…" : "Analyze session"}
                </button>
              </div>
              <div className="pagination">
                <span>{sessions?.total ?? 0} saved replay sessions</span>
                <div>
                  <button
                    aria-label="Previous compatibility session choices"
                    disabled={!sessionOffset}
                    onClick={() => setSessionOffset((v) => Math.max(0, v - 20))}
                  >
                    Previous
                  </button>
                  <button
                    aria-label="Next compatibility session choices"
                    disabled={sessionOffset + 20 >= (sessions?.total ?? 0)}
                    onClick={() => setSessionOffset((v) => v + 20)}
                  >
                    Next
                  </button>
                </div>
              </div>
            </section>
          )}
          {!run && (
            <div className="empty-state">
              <h3>
                {runId
                  ? "Opening saved analysis…"
                  : reportsOnly
                    ? "Select a saved report from history"
                    : "Choose a session to assess"}
              </h3>
              <p>
                {reportsOnly
                  ? "Reports use the immutable evidence and policy from each selected analysis."
                  : "Compare & analyze runs both steps on saved evidence. Existing configurations are reused."}
              </p>
              {sessionId && (
                <Link
                  to={`/comparisons?project=${project.id}&session=${sessionId}`}
                  className="text-button"
                >
                  Compare this session first
                </Link>
              )}
            </div>
          )}
          {run && (
            <section aria-label="Compatibility overview">
              <div
                className={`panel compatibility-verdict verdict-${run.verdict}`}
              >
                <div className="run-context">
                  {run.metadata_snapshot.session_name} ·{" "}
                  {new Date(run.analyzed_at).toLocaleString()}
                </div>
                <h2>{verdictLabels[run.verdict]}</h2>
                <p>
                  Applies to these recorded requests under the saved policy.
                  Unexecuted endpoints were not tested; this is not a universal
                  compatibility guarantee.
                </p>
                <ReportDownloads
                  key={run.id}
                  runId={run.id}
                  engineVersion={run.engine_version}
                />
                <p className="muted">
                  Exports contain safe previews and up to 500 findings, with any
                  omissions stated. Use the paginated findings below for the
                  full saved set.
                </p>
                {!run.is_current && (
                  <p className="warning-note">
                    This result has older policies/comparison rules or
                    incomplete comparison coverage. Compare with current rules
                    where needed, then select Analyze session. This historical
                    result remains available.
                  </p>
                )}
              </div>
              <div className="comparison-stat-grid compatibility-stats">
                {[
                  ["Replayed", "replayed"],
                  ["Compared", "compared"],
                  ["Identical", "identical"],
                  ["Changed", "changed"],
                  ["Confirmed breaking", "confirmed_breaking"],
                  ["Potentially breaking", "potentially_breaking"],
                  ["Informational", "informational"],
                  ["Unassessed", "unassessed"],
                  ["High / critical", "high_critical"],
                  ["Transport failures", "transport_failures"],
                ].map(([label, key]) => (
                  <div className="panel comparison-stat" key={key}>
                    <span>{label}</span>
                    <strong>{run.summary[key] ?? 0}</strong>
                  </div>
                ))}
              </div>
              {(run.summary.missing_comparisons > 0 ||
                run.summary.incomplete_comparisons > 0) && (
                <p className="warning-note">
                  Evidence coverage: {run.summary.missing_comparisons} missing
                  comparisons; {run.summary.incomplete_comparisons} incomplete
                  comparisons. Counts of classifications refer to findings, not
                  unique requests.
                </p>
              )}
              <Findings key={run.id} runId={run.id} />
              <details className="panel compatibility-snapshots">
                <summary>Frozen policies and source comparisons</summary>
                {run.analyses.map((a) => (
                  <details key={a.id}>
                    <summary>
                      {a.request_method} {a.endpoint_path} ·{" "}
                      {a.is_current
                        ? "Current settings"
                        : "Historical settings"}
                    </summary>
                    <p>
                      {verdictLabels[a.verdict]} · {a.counts.findings} findings
                    </p>
                    <Link
                      to={`/comparisons/${a.comparison_id}`}
                      className="text-button"
                    >
                      Open saved comparison
                    </Link>
                    <pre>
                      {JSON.stringify(
                        {
                          policy: a.effective_policy,
                          comparison_rules: a.effective_comparison_rules,
                          policy_hash: a.policy_hash,
                          engine: a.engine_version,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                ))}
                {!run.analyses.length && (
                  <p>No saved comparisons were available for this analysis.</p>
                )}
              </details>
            </section>
          )}
          {settings && !reportsOnly && (
            <PolicyEditor
              key={project.id}
              settings={settings}
              onSaved={(s) => {
                setSettings(s);
                setRevision((v) => v + 1);
              }}
            />
          )}
          <section
            className="panel comparison-history"
            aria-label="Compatibility history"
          >
            <div className="section-heading">
              <h2>Analysis history</h2>
              <span>Immutable policy and engine snapshots</span>
            </div>
            {history?.items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>SESSION / DATE</th>
                      <th>VERDICT</th>
                      <th>CONFIRMED / POTENTIAL / UNASSESSED</th>
                      <th>POLICY</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.items.map((r) => (
                      <tr key={r.id}>
                        <td>
                          <Link className="history-session" to={openRun(r)}>
                            <strong>{r.metadata_snapshot.session_name}</strong>
                            <small>
                              {new Date(r.analyzed_at).toLocaleString()}
                            </small>
                          </Link>
                        </td>
                        <td>{verdictLabels[r.verdict]}</td>
                        <td>
                          {r.summary.confirmed_breaking} /{" "}
                          {r.summary.potentially_breaking} /{" "}
                          {r.summary.unassessed}
                        </td>
                        <td>
                          {r.is_current ? "Current" : "Historical / incomplete"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <h3>No compatibility analyses yet</h3>
                <p>
                  Each distinct source comparison, policy and engine
                  configuration is preserved here.
                </p>
              </div>
            )}
            <div className="pagination">
              <span>{history?.total ?? 0} saved analyses</span>
              <div>
                <button
                  aria-label="Previous compatibility history"
                  disabled={!offset || loading}
                  onClick={() => setOffset((v) => Math.max(0, v - 20))}
                >
                  Previous
                </button>
                <button
                  aria-label="Next compatibility history"
                  disabled={loading || offset + 20 >= (history?.total ?? 0)}
                  onClick={() => setOffset((v) => v + 20)}
                >
                  Next
                </button>
              </div>
            </div>
          </section>
          <p className="compatibility-methodology">
            Confirmed = explicit requirement violated. Potential = structural or
            HTTP risk without proof. Informational = permitted or a documented
            default. Unassessed = insufficient context or evidence. Severity
            describes impact; confidence describes evidence strength, not
            probability.
          </p>
        </>
      )}
    </>
  );
}

import { useEffect, useState } from "react";
import {
  Link,
  useParams,
  useSearchParams,
  useNavigate,
} from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { compatibilityApi } from "../services/compatibilityApi";
import { replayApi } from "../services/replayApi";
import { errorMessage } from "../services/api";
import type { ReplayResult, ReplaySessionDetail } from "../types/replay";
import { ReplaySummary } from "../components/replay/ReplaySummary";
import { ResponseViewer } from "../components/replay/ResponseViewer";
export function ReplaySessionDetails({
  onProject,
}: {
  onProject: (id: string) => void;
}) {
  const navigate = useNavigate();
  const [assessing, setAssessing] = useState(false);
  const { id } = useParams(),
    [params, setParams] = useSearchParams();
  const [session, setSession] = useState<ReplaySessionDetail | null>(null),
    [result, setResult] = useState<ReplayResult | null>(null),
    [error, setError] = useState(""),
    [resultError, setResultError] = useState(""),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true,
      timer: ReturnType<typeof setTimeout>;
    setSession(null);
    setResult(null);
    setError("");
    const load = async () => {
      try {
        const data = await replayApi.session(id!);
        if (!live) return;
        setSession(data);
        onProject(data.project_id);
        setError("");
        if (data.status === "running") timer = setTimeout(load, 1500);
      } catch (e) {
        if (live) setError(errorMessage(e));
      }
    };
    void load();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [id, onProject, revision]);
  const selected =
    session?.results.find((r) => r.id === params.get("result"))?.id ||
    session?.results[0]?.id;
  useEffect(() => {
    if (!selected) return;
    let live = true;
    setResult(null);
    setResultError("");
    replayApi
      .result(selected)
      .then((r) => {
        if (live) setResult(r);
      })
      .catch((e) => {
        if (live) setResultError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [selected, session?.completed_requests, session?.status]);
  return (
    <>
      <div className="replay-navigation">
        <Link to="/replay/history" className="text-button">
          Replay history
        </Link>
        <Link to="/replay" className="text-button">
          Configure another replay
        </Link>
      </div>
      <div className="page-intro">
        <div>
          <h1>Replay results</h1>
          <p>Inspect the captured responses without changing the original.</p>
        </div>
        <button
          className="button secondary small"
          onClick={() => setRevision((v) => v + 1)}
        >
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>
      {error && (
        <div className="error-box mb-5" role="alert">
          {error}
        </div>
      )}
      {!session && !error ? (
        <div className="empty-state">
          <span className="spinner" />
          Loading session…
        </div>
      ) : (
        session && (
          <>
            <ReplaySummary session={session} />
            <div className="comparison-entry-link">
              <button
                className="button primary"
                disabled={assessing || session.status === "running"}
                onClick={async () => {
                  setAssessing(true);
                  setError("");
                  try {
                    const r = await compatibilityApi.assess(session.id);
                    navigate(
                      `/compatibility?project=${r.project_id}&session=${r.replay_session_id}&run=${r.id}`,
                    );
                  } catch (e) {
                    setError(errorMessage(e));
                  } finally {
                    setAssessing(false);
                  }
                }}
              >
                {assessing ? "Assessing saved evidence…" : "Compare & analyze"}
              </button>
              <Link
                className="button secondary"
                to={`/comparisons?project=${session.project_id}&session=${session.id}`}
              >
                Compare saved responses
              </Link>
            </div>
            {session.status === "interrupted" && (
              <div className="error-box my-5">
                An execution was interrupted. A request may have reached the
                target. Review the result before repeating a write.
              </div>
            )}
            <section
              className="panel replay-results"
              aria-label="Replay results"
            >
              <div className="section-heading">
                <h2>Requests in this run</h2>
                <span>{session.results.length} results</span>
              </div>
              {session.results.map((r) => (
                <button
                  key={r.id}
                  aria-pressed={selected === r.id}
                  aria-label={`Inspect ${r.request_method} ${r.endpoint_path}`}
                  className={`replay-result-row ${selected === r.id ? "selected" : ""}`}
                  onClick={() => setParams({ result: r.id })}
                >
                  <span className="result-order">
                    {String(r.ordinal + 1).padStart(2, "0")}
                  </span>
                  <span
                    className={`method method-${r.request_method.toLowerCase()}`}
                  >
                    {r.request_method}
                  </span>
                  <code>{r.endpoint_path}</code>
                  <span
                    className={`outcome ${r.outcome === "http_response" ? "" : "outcome-warning"}`}
                  >
                    {r.outcome.replaceAll("_", " ")}
                  </span>
                  <span className="mono">{r.response_status ?? "—"}</span>
                  <span className="mono muted">
                    {r.duration_ms.toFixed(0)} ms
                  </span>
                </button>
              ))}
            </section>
            {resultError ? (
              <div className="error-box" role="alert">
                {resultError}
              </div>
            ) : result ? (
              <ResponseViewer
                key={result.id + session.completed_requests}
                result={result}
              />
            ) : (
              <div className="empty-state">
                <span className="spinner" />
                Loading response snapshots…
              </div>
            )}
          </>
        )
      )}
    </>
  );
}

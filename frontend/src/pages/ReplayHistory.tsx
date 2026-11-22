import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ChevronLeft,
  ChevronRight,
  History,
  Plus,
  RefreshCw,
} from "lucide-react";
import type { Project } from "../types";
import type { ReplaySessionPage } from "../types/replay";
import { replayApi } from "../services/replayApi";
import { errorMessage } from "../services/api";
import { SessionStatus } from "../components/replay/ReplaySummary";
export function ReplayHistory({ project }: { project: Project }) {
  const [page, setPage] = useState<ReplaySessionPage | null>(null),
    [offset, setOffset] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    replayApi
      .sessions(project.id, offset)
      .then((p) => {
        if (live) {
          setPage(p);
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
  }, [project.id, offset, revision]);
  return (
    <>
      <div className="page-intro">
        <div>
          <h1>Replay history</h1>
          <p>Reopen a run and inspect its original and replayed responses.</p>
        </div>
        <Link className="button primary" to="/replay">
          <Plus size={15} />
          New replay
        </Link>
      </div>
      <section className="panel">
        <div className="section-heading">
          <span>{project.name}</span>
          <button
            className="icon-button"
            aria-label="Refresh replay history"
            onClick={() => setRevision((v) => v + 1)}
          >
            <RefreshCw size={15} />
          </button>
        </div>
        {error && (
          <div className="error-box m-4" role="alert">
            {error}
          </div>
        )}
        {loading ? (
          <div className="empty-state">
            <span className="spinner" />
            Loading replay sessions…
          </div>
        ) : !page?.items.length ? (
          <div className="empty-state">
            <History size={25} />
            <h3>No replay sessions yet</h3>
            <p>Select a recording and choose another approved target.</p>
            <Link className="text-button" to="/replay">
              Configure a replay
            </Link>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>SESSION / TARGET</th>
                  <th>REQUESTS</th>
                  <th>STARTED</th>
                  <th>STATUS</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <Link
                        className="history-session"
                        to={`/replay/sessions/${s.id}`}
                      >
                        <strong>{s.name}</strong>
                        <code>{s.target_base_url}</code>
                      </Link>
                    </td>
                    <td>
                      {s.completed_requests} / {s.total_requests}
                    </td>
                    <td>{new Date(s.started_at).toLocaleString()}</td>
                    <td>
                      <SessionStatus status={s.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pagination">
          <span>{page?.total ?? 0} sessions</span>
          <div>
            <button
              aria-label="Previous sessions"
              disabled={!offset || loading}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              <ChevronLeft size={16} />
            </button>
            <span>{Math.floor(offset / 20) + 1}</span>
            <button
              aria-label="Next sessions"
              disabled={loading || offset + 20 >= (page?.total ?? 0)}
              onClick={() => setOffset(offset + 20)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </section>
    </>
  );
}

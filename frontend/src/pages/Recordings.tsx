import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Flag,
  History,
  RefreshCw,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { api, errorMessage } from "../services/api";
import type { Project, Recording, RecordingPage } from "../types";
import { ResponsePanel, Status } from "../components/ResponsePanel";
export function Recordings({ project }: { project: Project }) {
  const [data, setData] = useState<RecordingPage | null>(null),
    [error, setError] = useState(""),
    [offset, setOffset] = useState(0),
    [search, setSearch] = useState(""),
    [method, setMethod] = useState(""),
    [baseline, setBaseline] = useState(false),
    [revision, setRevision] = useState(0),
    [loading, setLoading] = useState(true);
  const settledSearch = useDebouncedValue(search);
  useEffect(() => {
    let live = true;
    setLoading(true);
    api
      .recordings(project.id, offset, baseline, 20, settledSearch, method)
      .then((p) => {
        if (live) {
          setData(p);
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
  }, [project.id, offset, baseline, settledSearch, method, revision]);
  return (
    <>
      <div className="page-intro">
        <div>
          <h1>Recordings</h1>
          <p>Every request, preserved as a point in time.</p>
        </div>
        <Link className="button primary" to="/">
          New request
        </Link>
      </div>
      <section className="panel">
        <div className="recordings-toolbar">
          <div className="flex gap-2">
            <button
              className={`filter-button ${!baseline ? "selected" : ""}`}
              onClick={() => {
                setBaseline(false);
                setOffset(0);
              }}
            >
              All recordings
            </button>
            <button
              className={`filter-button ${baseline ? "selected" : ""}`}
              onClick={() => {
                setBaseline(true);
                setOffset(0);
              }}
            >
              <Flag size={13} />
              Baselines
            </button>
          </div>
          <button
            className="icon-button"
            aria-label="Refresh recordings"
            onClick={() => setRevision((v) => v + 1)}
          >
            <RefreshCw size={15} />
          </button>
        </div>
        <div className="recording-search">
          <label>
            Search recordings
            <input
              value={search}
              maxLength={200}
              placeholder="Name or endpoint"
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label>
            HTTP method filter
            <select
              value={method}
              onChange={(e) => {
                setMethod(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All methods</option>
              {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
        </div>
        {error && (
          <div className="error-box m-4" role="alert">
            {error}
          </div>
        )}
        {loading ? (
          <div className="empty-state">
            <span className="spinner" />
            <p>Loading recordings…</p>
          </div>
        ) : !data?.items.length ? (
          <div className="empty-state">
            <History size={24} />
            <h3>
              {search || method
                ? "No matching recordings"
                : baseline
                  ? "No baselines yet"
                  : "Your timeline starts here"}
            </h3>
            <p>
              {baseline
                ? "Open a recording and mark it as a baseline."
                : "Send your first request from the workspace."}
            </p>
          </div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>REQUEST / RECORDING</th>
                  <th>STATUS</th>
                  <th>DURATION</th>
                  <th>CAPTURED</th>
                  <th>LABEL</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link
                        className="table-request"
                        to={`/recordings/${r.id}`}
                      >
                        <span
                          className={`method method-${r.method.toLowerCase()}`}
                        >
                          {r.method}
                        </span>
                        <span>
                          <strong>{r.name}</strong>
                          <code>{r.endpoint_path}</code>
                        </span>
                        {r.is_baseline && <Flag size={13} className="accent" />}
                      </Link>
                    </td>
                    <td>
                      <Status record={r} />
                    </td>
                    <td className="mono">{r.duration_ms.toFixed(0)} ms</td>
                    <td>{new Date(r.captured_at).toLocaleString()}</td>
                    <td>
                      <span className="muted">
                        {r.environment_label || "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pagination">
          <span>{data?.total ?? 0} recordings</span>
          <div>
            <button
              aria-label="Previous page"
              disabled={!offset || loading}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              <ChevronLeft size={16} />
            </button>
            <span>{Math.floor(offset / 20) + 1}</span>
            <button
              aria-label="Next page"
              disabled={loading || offset + 20 >= (data?.total ?? 0)}
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
export function RecordingDetail({
  onProject,
}: {
  onProject: (id: string) => void;
}) {
  const { id } = useParams(),
    [record, setRecord] = useState<Recording | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    setRecord(null);
    api
      .recording(id!)
      .then((r) => {
        if (live) {
          setRecord(r);
          onProject(r.project_id);
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
  }, [id, onProject]);
  return (
    <>
      <Link
        to={record ? `/recordings?project=${record.project_id}` : "/recordings"}
        className="text-button mb-7"
      >
        Back to recordings
      </Link>
      <div className="page-intro">
        <div>
          <h1>Recording detail</h1>
          {record && (
            <Link
              className="button secondary small mt-4"
              to={`/replay?recording=${record.id}&project=${record.project_id}`}
            >
              Replay this recording
            </Link>
          )}
          <p className="mono break-all">
            {record
              ? `${record.method} ${record.base_url}${record.endpoint_path}`
              : "Loading capture…"}
          </p>
        </div>
      </div>
      {error ? (
        <div className="error-box" role="alert">
          {error}
        </div>
      ) : (
        <ResponsePanel record={record} busy={loading} onUpdate={setRecord} />
      )}
    </>
  );
}

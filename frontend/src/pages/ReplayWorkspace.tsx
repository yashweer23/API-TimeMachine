import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  History,
  Plus,
  RotateCw,
  ShieldCheck,
  X,
} from "lucide-react";
import type {
  Project,
  Recording,
  RecordingPage,
  RecordingSummary,
} from "../types";
import type { ReplayConfig, ReplayDraft, ReplayPayload } from "../types/replay";
import { emptyDraft } from "../types/replay";
import { api, errorMessage } from "../services/api";
import { replayApi } from "../services/replayApi";
import { prepareReplay } from "../services/replayPreparation";
import { pairsToObject, type Pair } from "../components/KeyValueEditor";
import { CodeView } from "../components/CodeView";
export function ReplayWorkspace({ project }: { project: Project }) {
  const navigate = useNavigate(),
    [search] = useSearchParams(),
    initial = search.get("recording");
  const [config, setConfig] = useState<ReplayConfig | null>(null),
    [page, setPage] = useState<RecordingPage | null>(null),
    [offset, setOffset] = useState(0),
    [listLoading, setListLoading] = useState(true),
    [selected, setSelected] = useState<Recording[]>([]),
    [selectionLoading, setSelectionLoading] = useState(false),
    [name, setName] = useState("API v2 regression run"),
    [target, setTarget] = useState(""),
    [headers, setHeaders] = useState<Pair[]>([]),
    [drafts, setDrafts] = useState<Record<string, ReplayDraft>>({}),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [confirm, setConfirm] = useState(false),
    [revision, setRevision] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    let live = true;
    replayApi
      .config()
      .then((c) => {
        if (live) {
          setConfig(c);
          setTarget(
            c.sample_v2_base_url ||
              c.allowed_target_origins.find((u) => u.includes("v2")) ||
              project.base_url,
          );
        }
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [project.base_url, revision]);
  useEffect(() => {
    let live = true;
    setListLoading(true);
    api
      .recordings(project.id, offset, false, 20)
      .then((p) => {
        if (live) setPage(p);
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      })
      .finally(() => {
        if (live) setListLoading(false);
      });
    return () => {
      live = false;
    };
  }, [project.id, offset, revision]);
  useEffect(() => {
    if (!initial) return;
    let live = true;
    setSelectionLoading(true);
    api
      .recording(initial)
      .then((r) => {
        if (live) {
          if (r.project_id !== project.id)
            throw new Error("Choose the project that owns this recording.");
          setSelected([r]);
        }
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      })
      .finally(() => {
        if (live) setSelectionLoading(false);
      });
    return () => {
      live = false;
    };
  }, [initial, project.id]);
  useEffect(() => {
    if (confirm) dialog.current?.showModal();
    else dialog.current?.close();
  }, [confirm]);
  const toggle = async (record: RecordingSummary) => {
    if (selected.some((r) => r.id === record.id)) {
      setSelected((s) => s.filter((r) => r.id !== record.id));
      setDrafts((d) => {
        const next = { ...d };
        delete next[record.id];
        return next;
      });
      return;
    }
    setSelectionLoading(true);
    setError("");
    try {
      const full = await api.recording(record.id);
      if (alive.current) setSelected((s) => [...s, full]);
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    } finally {
      if (alive.current) setSelectionLoading(false);
    }
  };
  const setDraft = (id: string, value: Partial<ReplayDraft>) =>
    setDrafts((d) => ({
      ...d,
      [id]: { ...(d[id] || emptyDraft()), ...value },
    }));
  let validation = "",
    payload: ReplayPayload | null = null;
  if (config)
    try {
      if (!name.trim()) throw new Error("Enter a session name.");
      const temp = pairsToObject(headers) as Record<string, string>;
      const overrides = prepareReplay(selected, drafts, temp, target, config);
      payload = {
        name: name.trim(),
        target_base_url: target,
        recording_ids: selected.map((r) => r.id),
        temporary_headers: temp,
        overrides,
        confirm_side_effects: false,
      };
    } catch (e) {
      validation = errorMessage(e);
    }
  const execute = async (confirmed: boolean) => {
    if (!payload || busy) return;
    setConfirm(false);
    setBusy(true);
    setError("");
    const data = { ...payload, confirm_side_effects: confirmed };
    setHeaders([]);
    setDrafts({});
    try {
      const session = await replayApi.create(project.id, data);
      if (alive.current) navigate(`/replay/sessions/${session.id}`);
    } catch (e) {
      if (alive.current)
        setError(
          errorMessage(e) + " Check replay history before repeating a write.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  };
  const start = () => {
    if (selected.some((r) => r.method !== "GET")) setConfirm(true);
    else void execute(false);
  };
  return (
    <>
      <div className="page-intro">
        <div>
          <h1>Replay workspace</h1>
          <p>Take a saved request to a new target. Keep both responses.</p>
        </div>
        <Link className="button secondary" to="/replay/history">
          <History size={14} />
          Replay history
        </Link>
      </div>
      {error && (
        <div className="error-box mb-5" role="alert">
          {error}
          <button
            className="text-button ml-auto"
            onClick={() => {
              setError("");
              setRevision((v) => v + 1);
            }}
          >
            Reload
          </button>
        </div>
      )}
      {busy ? (
        <section className="panel replay-running" role="status">
          <span className="spinner" />
          <h2>
            Executing {selected.length}{" "}
            {selected.length === 1 ? "request" : "requests"} sequentially
          </h2>
          <p>
            Request execution budget: {config?.session_timeout_seconds} seconds.
          </p>
          <p>
            Keep this page open. If you leave, check history before repeating a
            write.
          </p>
          <span className="subtle-label">NO AUTOMATIC RETRIES</span>
        </section>
      ) : (
        <div className="replay-workspace-grid">
          <section
            className="panel recording-selector"
            aria-label="Recording selection"
          >
            <div className="section-heading">
              <div>
                <h2>Select recordings</h2>
                <p>
                  {selected.length} selected · maximum{" "}
                  {config?.max_batch_size ?? "—"}
                </p>
              </div>
              <Link className="text-button" to="/">
                New capture
                <Plus size={13} />
              </Link>
            </div>
            {listLoading ? (
              <div className="empty-state">
                <span className="spinner" />
                Loading recordings…
              </div>
            ) : !page?.items.length ? (
              <div className="empty-state">
                <RotateCw size={24} />
                <h3>Record a request first</h3>
                <p>Your saved requests will appear here.</p>
                <Link to="/" className="button secondary small">
                  Open workspace
                </Link>
              </div>
            ) : (
              <div>
                {page.items.map((r) => {
                  const checked = selected.some((s) => s.id === r.id);
                  return (
                    <label
                      className={`recording-choice ${checked ? "checked" : ""}`}
                      key={r.id}
                    >
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.name}`}
                        checked={checked}
                        disabled={
                          selectionLoading ||
                          (!checked &&
                            selected.length >= (config?.max_batch_size ?? 0))
                        }
                        onChange={() => void toggle(r)}
                      />
                      <span
                        className={`method method-${r.method.toLowerCase()}`}
                      >
                        {r.method}
                      </span>
                      <span className="choice-text">
                        <strong>{r.name}</strong>
                        <code>{r.endpoint_path}</code>
                        <small>
                          {new Date(r.captured_at).toLocaleString()}
                        </small>
                      </span>
                      <span className="choice-status">
                        {r.response_status ?? "Failed"}
                        {r.is_baseline && <small>BASELINE</small>}
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
            <div className="pagination">
              <span>{page?.total ?? 0} recordings</span>
              <div>
                <button
                  aria-label="Previous recordings"
                  disabled={!offset || listLoading}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
                >
                  <ChevronLeft size={15} />
                </button>
                <span>{Math.floor(offset / 20) + 1}</span>
                <button
                  aria-label="Next recordings"
                  disabled={listLoading || offset + 20 >= (page?.total ?? 0)}
                  onClick={() => setOffset(offset + 20)}
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </section>
          <section
            className="panel replay-configuration"
            aria-label="Replay configuration"
          >
            <div className="section-heading">
              <h2>Configure this run</h2>
              <ShieldCheck size={16} />
            </div>
            <div className="replay-config-fields">
              <label>
                Session name
                <input
                  aria-label="Session name"
                  value={name}
                  maxLength={160}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label>
                Target base URL
                <input
                  aria-label="Replay target base URL"
                  list="approved-replay-targets"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder="http://sample-api-v2:8001"
                />
              </label>
              <datalist id="approved-replay-targets">
                {config?.allowed_target_origins.map((u) => (
                  <option value={u} key={u} />
                ))}
              </datalist>
              <p className="field-note">
                Only configured targets are allowed. Existing recordings keep
                their original URLs and responses.
              </p>
              <details className="temporary-credentials">
                <summary>
                  Temporary headers <span>optional</span>
                </summary>
                <p>
                  Used only for this run. Values and recognized echoes are
                  redacted; these fields clear when execution starts.
                </p>
                {headers.map((row, index) => (
                  <div className="temporary-header-row" key={row.id}>
                    <input
                      aria-label={`Temporary header name ${index + 1}`}
                      placeholder="Authorization"
                      value={row.key}
                      onChange={(e) =>
                        setHeaders((rows) =>
                          rows.map((r) =>
                            r.id === row.id ? { ...r, key: e.target.value } : r,
                          ),
                        )
                      }
                    />
                    <input
                      type="password"
                      autoComplete="off"
                      aria-label={`Temporary header value ${index + 1}`}
                      placeholder="Bearer …"
                      value={row.value}
                      onChange={(e) =>
                        setHeaders((rows) =>
                          rows.map((r) =>
                            r.id === row.id
                              ? { ...r, value: e.target.value }
                              : r,
                          ),
                        )
                      }
                    />
                    <button
                      className="icon-button"
                      aria-label={`Remove temporary header ${index + 1}`}
                      onClick={() =>
                        setHeaders((rows) =>
                          rows.filter((r) => r.id !== row.id),
                        )
                      }
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
                <button
                  className="text-button"
                  onClick={() =>
                    setHeaders((rows) => [
                      ...rows,
                      { id: Date.now(), key: "", value: "" },
                    ])
                  }
                >
                  <Plus size={13} />
                  Add temporary header
                </button>
              </details>
            </div>
          </section>
          {selected.length > 0 && (
            <section className="panel replay-review">
              <div className="section-heading">
                <h2>Review selected requests</h2>
                <span>Order of selection = execution order</span>
              </div>
              {selected.map((r, i) => (
                <details className="review-request" key={r.id}>
                  <summary>
                    <span className="muted">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className={`method method-${r.method.toLowerCase()}`}>
                      {r.method}
                    </span>
                    <code>{r.endpoint_path}</code>
                    <span className="ml-auto muted">Inspect / override</span>
                  </summary>
                  <div className="review-content">
                    <p className="field-note">
                      {r.name} · {r.base_url}. Method and endpoint are
                      preserved.
                    </p>
                    {r.request_body_present === null && (
                      <p className="warning-note">
                        Legacy capture: explicitly choose No body, or replace
                        with JSON null.
                      </p>
                    )}
                    <div className="override-grid">
                      <label>
                        Header overrides (JSON; null removes a header)
                        <textarea
                          aria-label={`Header overrides for ${r.id}`}
                          placeholder={'{"Cookie": null}'}
                          spellCheck={false}
                          value={drafts[r.id]?.headers || ""}
                          onChange={(e) =>
                            setDraft(r.id, { headers: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Replace query parameters (JSON)
                        <textarea
                          aria-label={`Query overrides for ${r.id}`}
                          placeholder="Leave blank to keep the original"
                          spellCheck={false}
                          value={drafts[r.id]?.query || ""}
                          onChange={(e) =>
                            setDraft(r.id, { query: e.target.value })
                          }
                        />
                      </label>
                    </div>
                    <label>
                      Request body
                      <select
                        aria-label={`Body mode for ${r.id}`}
                        value={drafts[r.id]?.bodyMode || "keep"}
                        onChange={(e) =>
                          setDraft(r.id, {
                            bodyMode: e.target.value as ReplayDraft["bodyMode"],
                          })
                        }
                      >
                        <option value="keep">Keep original body</option>
                        <option value="omit">No body</option>
                        <option value="replace">Replace with JSON</option>
                      </select>
                    </label>
                    {drafts[r.id]?.bodyMode === "replace" && (
                      <textarea
                        className="override-body"
                        aria-label={`Body override for ${r.id}`}
                        spellCheck={false}
                        placeholder="Enter JSON, including null if intended"
                        value={drafts[r.id]?.body || ""}
                        onChange={(e) =>
                          setDraft(r.id, { body: e.target.value })
                        }
                      />
                    )}
                    <p className="field-note">
                      All supplied override values are treated as temporary.
                      Matching response values may also be masked.
                    </p>
                    <details>
                      <summary className="text-button">
                        View saved request
                      </summary>
                      <CodeView
                        value={{
                          headers: r.request_headers,
                          query_parameters: r.query_parameters,
                          body: r.request_body,
                          body_present: r.request_body_present,
                        }}
                      />
                    </details>
                  </div>
                </details>
              ))}
            </section>
          )}
          <div className="replay-launch">
            <div>
              {validation && (
                <p className="validation-note" role="status">
                  {validation}
                </p>
              )}
              <p className="muted text-xs">
                Original snapshots stay unchanged. Each run creates its own
                history.
              </p>
            </div>
            <button
              className="button primary"
              disabled={!payload || !config || selectionLoading}
              onClick={start}
            >
              <RotateCw size={15} />
              Run replay
            </button>
          </div>
        </div>
      )}
      <dialog
        ref={dialog}
        className="project-dialog replay-confirm"
        onCancel={() => setConfirm(false)}
      >
        <AlertTriangle size={25} className="warning-icon" />
        <h2>These requests can change data</h2>
        <p>
          POST, PUT, PATCH, and DELETE requests may create, update, or remove
          data at the target. They will be executed once, without automatic
          retries.
        </p>
        <code className="confirm-target">{target}</code>
        <ul>
          {selected
            .filter((r) => r.method !== "GET")
            .map((r) => (
              <li key={r.id}>
                <strong>{r.method}</strong> {r.endpoint_path}
              </li>
            ))}
        </ul>
        <div className="dialog-actions">
          <button
            className="button secondary"
            onClick={() => setConfirm(false)}
          >
            Cancel
          </button>
          <button className="button primary" onClick={() => void execute(true)}>
            Confirm and run
          </button>
        </div>
      </dialog>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { Flag, History, Send, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { parseJsonInput } from "../services/jsonInput";
import { api, errorMessage } from "../services/api";
import type {
  Project,
  Recording,
  RecordingSummary,
  SendPayload,
} from "../types";
import {
  KeyValueEditor,
  pairsToObject,
  type Pair,
} from "../components/KeyValueEditor";
import { ResponsePanel, Status } from "../components/ResponsePanel";
export function Workspace({ project }: { project: Project }) {
  const [method, setMethod] = useState("GET"),
    [path, setPath] = useState("/users"),
    [tab, setTab] = useState("Parameters"),
    [body, setBody] = useState(""),
    [name, setName] = useState(""),
    [label, setLabel] = useState("v1 · local");
  const [params, setParams] = useState<Pair[]>([{ id: 1, key: "", value: "" }]),
    [headers, setHeaders] = useState<Pair[]>([{ id: 1, key: "", value: "" }]);
  const [record, setRecord] = useState<Recording | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [recentError, setRecentError] = useState(""),
    [recent, setRecent] = useState<RecordingSummary[]>([]),
    [revision, setRevision] = useState(0),
    [pending, setPending] = useState<SendPayload | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (pending) dialog.current?.showModal();
    else dialog.current?.close();
  }, [pending]);
  let bodyError = "";
  if (body.trim())
    try {
      parseJsonInput(body, "Request body");
    } catch (e) {
      bodyError = errorMessage(e);
    }
  useEffect(() => {
    let live = true;
    api
      .recordings(project.id, 0, false, 6)
      .then((p) => {
        if (live) {
          setRecent(p.items);
          setRecentError("");
        }
      })
      .catch((e) => {
        if (live) setRecentError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [project.id, revision]);
  const updated = (r: Recording) => {
    setRecord(r);
    setRevision((v) => v + 1);
  };
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError("");
    let payload: SendPayload;
    try {
      payload = {
        method,
        endpoint_path: path,
        headers: pairsToObject(headers) as Record<string, string>,
        query_parameters: pairsToObject(params, true),
        ...(name ? { name } : {}),
        ...(label ? { environment_label: label } : {}),
        ...(body.trim() ? { body: parseJsonInput(body, "Request body") } : {}),
      };
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? "The request body is not valid JSON. Check the Body tab."
          : errorMessage(e),
      );
      setTab("Body");
      return;
    }
    if (method !== "GET") {
      setPending(payload);
      return;
    }
    await execute(payload);
  };
  const execute = async (payload: SendPayload) => {
    if (busy) return;
    setPending(null);
    setBusy(true);
    try {
      updated(await api.send(project.id, payload));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const example = (m: string, p: string) => {
    setMethod(m);
    setPath(p);
    setBody(
      m === "POST"
        ? '{\n  "message": "Hello, TimeMachine",\n  "version": 1\n}'
        : "",
    );
    setTab(m === "POST" ? "Body" : "Parameters");
    setName("");
  };
  return (
    <>
      <dialog
        ref={dialog}
        className="project-dialog"
        onCancel={() => setPending(null)}
      >
        <h2>Confirm API request</h2>
        <p className="muted">
          {pending?.method} {pending?.endpoint_path} may change data on the
          target API. It will execute once and will not retry automatically.
        </p>
        <code className="break-all">{project.base_url}</code>
        <div className="dialog-actions">
          <button className="button secondary" onClick={() => setPending(null)}>
            Cancel
          </button>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => {
              if (pending) void execute(pending);
            }}
          >
            Confirm send request
          </button>
        </div>
      </dialog>
      <div className="page-intro">
        <div>
          <h1>Request workspace</h1>
          <p>Build a request and inspect the saved response.</p>
        </div>
        <span className="workspace-save-note">
          <ShieldCheck size={14} />
          Requests save automatically
        </span>
      </div>
      <div className="workspace-grid">
        <div className="request-column">
          <section className="panel request-panel">
            <div className="request-title">
              Request
              <span className="muted ml-auto text-xs">{project.name}</span>
            </div>
            <form onSubmit={send}>
              <fieldset disabled={busy || !!pending}>
                <div className="target-line">
                  <span>Target</span>
                  <code title={project.base_url}>{project.base_url}</code>
                  <ShieldCheck size={13} />
                </div>
                <div className="send-row">
                  <select
                    aria-label="HTTP method"
                    value={method}
                    onChange={(e) => setMethod(e.target.value)}
                    className={`method-select method-${method.toLowerCase()}`}
                  >
                    {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => (
                      <option key={m}>{m}</option>
                    ))}
                  </select>
                  <input
                    aria-label="Endpoint path"
                    required
                    value={path}
                    onChange={(e) => setPath(e.target.value)}
                    placeholder="/users"
                  />
                  <button
                    className="button primary send-button"
                    type="submit"
                    disabled={busy || !!bodyError}
                  >
                    <Send size={15} />
                    {busy ? "Sending…" : "Send request"}
                  </button>
                </div>
                <div className="tabs">
                  {["Parameters", "Headers", "Body", "Details"].map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setTab(t)}
                      className={tab === t ? "active" : ""}
                    >
                      {t}
                      {t === "Body" && body.trim() && (
                        <span className="dot tiny" />
                      )}
                    </button>
                  ))}
                </div>
                <div className="request-editor">
                  {tab === "Parameters" ? (
                    <KeyValueEditor
                      label="Parameter"
                      rows={params}
                      onChange={setParams}
                      disabled={busy}
                    />
                  ) : tab === "Headers" ? (
                    <>
                      <KeyValueEditor
                        label="Header"
                        rows={headers}
                        onChange={setHeaders}
                        disabled={busy}
                      />
                      <p className="field-note">
                        Credentials are sent to the target but redacted from
                        saved recordings.
                      </p>
                    </>
                  ) : tab === "Body" ? (
                    <>
                      <div className="editor-caption">
                        <span>JSON</span>
                        <span>Leave empty for no body</span>
                      </div>
                      <button
                        type="button"
                        className="text-button"
                        disabled={!body.trim() || !!bodyError}
                        onClick={() =>
                          setBody(
                            JSON.stringify(
                              parseJsonInput(body, "Request body"),
                              null,
                              2,
                            ),
                          )
                        }
                      >
                        Format JSON
                      </button>
                      <textarea
                        aria-invalid={!!bodyError}
                        aria-describedby={
                          bodyError ? "request-body-error" : undefined
                        }
                        className="body-editor"
                        aria-label="JSON request body"
                        spellCheck={false}
                        value={body}
                        onChange={(e) => setBody(e.target.value)}
                        placeholder={'{\n  "message": "Hello, TimeMachine"\n}'}
                      />
                    </>
                  ) : (
                    <div className="details-editor">
                      <label>
                        Recording name
                        <input
                          aria-label="New recording name"
                          maxLength={160}
                          placeholder={`${method} ${path}`}
                          value={name}
                          onChange={(e) => setName(e.target.value)}
                        />
                      </label>
                      <label>
                        Environment / version
                        <input
                          aria-label="Environment label"
                          maxLength={80}
                          placeholder="v1 · staging"
                          value={label}
                          onChange={(e) => setLabel(e.target.value)}
                        />
                      </label>
                    </div>
                  )}
                </div>
              </fieldset>
            </form>
            {bodyError && (
              <div
                id="request-body-error"
                role="alert"
                className="error-box m-4"
              >
                {bodyError}
              </div>
            )}
            {error && error !== bodyError && (
              <div className="error-box m-4" role="alert">
                {error}
              </div>
            )}
            <div className="panel-footnote">
              <ShieldCheck size={13} />
              Sanitized before storage
            </div>
          </section>
          <ResponsePanel record={record} busy={busy} onUpdate={updated} />
        </div>
        <aside className="context-column">
          <section className="context-section">
            <div className="section-label">Quick requests</div>
            <p className="muted text-xs mb-4 leading-relaxed">
              Endpoints available in the included sample API.
            </p>
            {[
              ["GET", "/users", "List all users"],
              ["GET", "/users/1", "Inspect one user"],
              ["GET", "/products", "Browse products"],
              ["POST", "/echo", "Send a JSON payload"],
            ].map(([m, p, d]) => (
              <button
                disabled={busy}
                className="example-button"
                key={p}
                onClick={() => example(m, p)}
              >
                <span>
                  <span className={`method method-${m.toLowerCase()}`}>
                    {m}
                  </span>
                  <code>{p}</code>
                </span>
                <span className="example-description">{d}</span>
              </button>
            ))}
          </section>
          <section className="context-section">
            <div className="section-label">
              <span className="flex items-center gap-2">
                <History size={14} />
                Recent recordings
              </span>
              <Link
                to="/recordings"
                className="text-button"
                aria-label="View all recordings"
              >
                View all
              </Link>
            </div>
            {recentError && <p className="error-box">{recentError}</p>}
            {!recent.length && !recentError ? (
              <p className="muted text-xs leading-relaxed">
                No captures yet.
                <br />
                Your request history will appear here.
              </p>
            ) : (
              recent.map((r) => (
                <Link
                  className="recent-row"
                  key={r.id}
                  to={`/recordings/${r.id}`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`method method-${r.method.toLowerCase()}`}>
                      {r.method}
                    </span>
                    <span className="truncate mono text-xs">
                      {r.endpoint_path}
                    </span>
                    {r.is_baseline && (
                      <Flag size={12} className="accent ml-auto" />
                    )}
                  </div>
                  <div className="flex justify-between mt-2">
                    <Status record={r} />
                    <span className="muted text-xs">
                      {r.duration_ms.toFixed(0)} ms
                    </span>
                  </div>
                </Link>
              ))
            )}
          </section>
        </aside>
      </div>
    </>
  );
}

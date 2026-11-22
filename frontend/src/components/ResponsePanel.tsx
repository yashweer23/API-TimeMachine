import { useEffect, useState } from "react";
import {
  Check,
  CircleAlert,
  Clock3,
  Copy,
  Flag,
  Radio,
  Save,
  ShieldCheck,
} from "lucide-react";
import type { Recording } from "../types";
import { api, errorMessage } from "../services/api";
import { CodeView } from "./CodeView";
export function Status({
  record,
}: {
  record: Pick<Recording, "response_status" | "execution_error">;
}) {
  return (
    <span
      className={`status ${record.execution_error || (record.response_status ?? 0) >= 400 ? "status-error" : ""}`}
    >
      {record.response_status ?? "Failed"}
      {record.execution_error && record.response_status ? " · incomplete" : ""}
    </span>
  );
}
export function ResponsePanel({
  record,
  busy = false,
  onUpdate,
}: {
  record: Recording | null;
  busy?: boolean;
  onUpdate: (record: Recording) => void;
}) {
  const [tab, setTab] = useState("Body"),
    [editing, setEditing] = useState(false),
    [name, setName] = useState(""),
    [label, setLabel] = useState(""),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [copied, setCopied] = useState(false);
  useEffect(() => {
    setName(record?.name ?? "");
    setLabel(record?.environment_label ?? "");
    setEditing(false);
    setError("");
    setCopied(false);
  }, [record?.id]);
  const patch = async (data: {
    name?: string;
    environment_label?: string | null;
    is_baseline?: boolean;
  }) => {
    if (!record) return;
    setSaving(true);
    setError("");
    try {
      onUpdate(await api.updateRecording(record.id, data));
      setEditing(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(
        record?.response_body_kind === "text"
          ? String(record.response_body)
          : JSON.stringify(record?.response_body, null, 2),
      );
      setCopied(true);
    } catch {
      setError("Clipboard is unavailable. Select and copy the response text.");
    }
  };
  return (
    <section className="panel response-panel" aria-label="Response">
      <div className="panel-heading">
        <div className="flex items-center gap-2">
          <Radio size={15} />
          <h2>Response</h2>
          {record && <Status record={record} />}
        </div>
        {record && (
          <span className="mono muted text-xs flex items-center gap-1">
            <Clock3 size={12} />
            {record.duration_ms.toFixed(0)} ms
          </span>
        )}
      </div>
      {busy ? (
        <div className="empty-state">
          <span className="spinner" />
          <h3>Capturing response</h3>
          <p>Executing your request and saving a sanitized snapshot.</p>
        </div>
      ) : !record ? (
        <div className="empty-state">
          <Radio size={28} strokeWidth={1.5} aria-hidden="true" />
          <h3>No response yet</h3>
          <p>
            Send a request to inspect its response.
            <br />
            Every execution is saved automatically.
          </p>
        </div>
      ) : (
        <>
          {record.execution_error && (
            <div className="error-box m-4" role="alert">
              <CircleAlert size={16} />
              <div>
                <strong>
                  {record.execution_error.code.replaceAll("_", " ")}
                </strong>
                <p>{record.execution_error.message}</p>
              </div>
            </div>
          )}
          <div className="tabs">
            <div className="flex">
              {["Body", "Headers", "Request"].map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={tab === t ? "active" : ""}
                >
                  {t}
                  {t === "Headers" && (
                    <span className="tab-count">
                      {Object.keys(record.response_headers).length}
                    </span>
                  )}
                </button>
              ))}
            </div>
            <button
              className="icon-button"
              aria-label="Copy response"
              onClick={copy}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
          <div className="response-content">
            {tab === "Body" ? (
              record.response_body_kind === "empty" ? (
                <p className="muted p-5">The target returned an empty body.</p>
              ) : record.response_body_kind === "omitted" ? (
                <p className="muted p-5">No response body was saved.</p>
              ) : (
                <CodeView
                  value={record.response_body}
                  plain={record.response_body_kind === "text"}
                />
              )
            ) : tab === "Headers" ? (
              <CodeView value={record.response_headers} />
            ) : (
              <div>
                <div className="request-summary">
                  <span
                    className={`method method-${record.method.toLowerCase()}`}
                  >
                    {record.method}
                  </span>
                  <span>
                    {record.base_url}
                    {record.endpoint_path}
                  </span>
                </div>
                <CodeView
                  value={{
                    query_parameters: record.query_parameters,
                    headers: record.request_headers,
                    body: record.request_body,
                  }}
                />
              </div>
            )}
          </div>
          <div className="recording-footer">
            <div className="flex items-start gap-2 min-w-0">
              <ShieldCheck size={15} className="accent shrink-0 mt-1" />
              <div className="min-w-0">
                <button
                  className="recording-name"
                  onClick={() => setEditing(!editing)}
                  title="Edit recording metadata"
                >
                  {record.name}
                </button>
                <p className="muted text-xs">
                  Saved · {new Date(record.captured_at).toLocaleString()}
                  {record.environment_label
                    ? ` · ${record.environment_label}`
                    : ""}
                </p>
              </div>
            </div>
            <button
              disabled={saving || !!record.execution_error}
              className={`button small ${record.is_baseline ? "baseline-button" : "secondary"}`}
              onClick={() => patch({ is_baseline: !record.is_baseline })}
            >
              <Flag size={13} />
              {record.is_baseline ? "Baseline" : "Mark baseline"}
            </button>
          </div>
          {editing && (
            <form
              className="metadata-form"
              onSubmit={(e) => {
                e.preventDefault();
                void patch({ name, environment_label: label || null });
              }}
            >
              <label>
                Recording name
                <input
                  aria-label="Recording name"
                  required
                  maxLength={160}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label>
                Environment / version
                <input
                  aria-label="Recording environment"
                  maxLength={80}
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                />
              </label>
              <button className="button primary small" disabled={saving}>
                <Save size={14} />
                Save changes
              </button>
            </form>
          )}
        </>
      )}
      {error && (
        <div className="error-box m-4" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}

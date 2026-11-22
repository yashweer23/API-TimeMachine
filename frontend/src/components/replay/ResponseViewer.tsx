import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { CodeView } from "../CodeView";
import { Status } from "../ResponsePanel";
import type { Json, Recording } from "../../types";
import type { ReplayResult } from "../../types/replay";
export function ResponseViewer({ result }: { result: ReplayResult }) {
  const [tab, setTab] = useState("Body");
  const original = result.original_recording;
  return (
    <section
      className="response-comparison"
      aria-label="Original and replayed responses"
    >
      <div className="comparison-toolbar">
        <div className="flex gap-5">
          {["Body", "Headers", "Request"].map((t) => (
            <button
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
              key={t}
            >
              {t}
            </button>
          ))}
        </div>
        <span>Manual inspection · no automatic comparison</span>
      </div>
      <div className="comparison-grid">
        <Snapshot
          label="Original recording"
          method={original.method}
          url={original.base_url + original.endpoint_path}
          record={original}
          timestamp={original.captured_at}
          content={
            tab === "Headers"
              ? original.response_headers
              : tab === "Request"
                ? {
                    headers: original.request_headers,
                    query_parameters: original.query_parameters,
                    body: original.request_body,
                    body_present: original.request_body_present,
                  }
                : original.response_body
          }
          kind={tab === "Body" ? original.response_body_kind : "json"}
        />
        <Snapshot
          label="Replayed response"
          method={result.request_method}
          url={result.replay_url}
          record={result}
          timestamp={result.executed_at}
          content={
            tab === "Headers"
              ? result.response_headers
              : tab === "Request"
                ? result.request_metadata
                : result.response_body
          }
          kind={tab === "Body" ? result.response_body_kind : "json"}
          outcome={result.outcome}
        />
      </div>
    </section>
  );
}
function Snapshot({
  label,
  method,
  url,
  record,
  timestamp,
  content,
  kind,
  outcome,
}: {
  label: string;
  method: string;
  url: string;
  record: Pick<
    Recording,
    "response_status" | "duration_ms" | "execution_error"
  >;
  timestamp: string | null;
  content: Json | object;
  kind: string;
  outcome?: string;
}) {
  const [copied, setCopied] = useState(false),
    [error, setError] = useState("");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(
        kind === "text" ? String(content) : JSON.stringify(content, null, 2),
      );
      setCopied(true);
      setError("");
    } catch {
      setError("Clipboard unavailable. Select and copy the displayed text.");
    }
  };
  const waiting = outcome === "pending" || outcome === "running";
  return (
    <article className="snapshot-panel" aria-label={label}>
      <div className="snapshot-heading">
        <h3>{label}</h3>
        <button
          aria-label={`Copy ${label.toLowerCase()}`}
          className="icon-button"
          disabled={kind === "omitted" || kind === "empty" || waiting}
          onClick={copy}
        >
          {copied ? <Check size={15} /> : <Copy size={15} />}
        </button>
      </div>
      <div className="snapshot-url">
        <span className={`method method-${method.toLowerCase()}`}>
          {method}
        </span>
        <code>{url}</code>
      </div>
      <div className="snapshot-meta">
        {waiting ? (
          <span className="muted">{outcome}</span>
        ) : record.response_status === null ? (
          <span className="muted">No HTTP response</span>
        ) : (
          <Status record={record} />
        )}
        <span>{record.duration_ms.toFixed(0)} ms</span>
      </div>
      {record.execution_error && (
        <div className="error-box m-3" role="alert">
          <div>
            <strong>{record.execution_error.code.replaceAll("_", " ")}</strong>
            <p>{record.execution_error.message}</p>
          </div>
        </div>
      )}
      <div className="snapshot-content">
        {waiting ? (
          <p className="muted p-5">Waiting for this request to finish.</p>
        ) : kind === "omitted" ? (
          <p className="muted p-5">No response body was saved.</p>
        ) : kind === "empty" ? (
          <p className="muted p-5">Empty response body.</p>
        ) : (
          <CodeView value={content} plain={kind === "text"} />
        )}
      </div>
      <div className="snapshot-time">
        {timestamp ? new Date(timestamp).toLocaleString() : "Not executed"}
        {error && <p role="alert">{error}</p>}
      </div>
    </article>
  );
}

import { useState } from "react";
import { Download } from "lucide-react";
import { errorMessage } from "../../services/api";
export function ReportDownloads({
  runId,
  engineVersion,
}: {
  runId: string;
  engineVersion: string;
}) {
  const [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const download = async (format: "json" | "html") => {
    if (busy) return;
    setBusy(format);
    setError("");
    try {
      const response = await fetch(
        `/api/compatibility-runs/${runId}/report?format=${format}`,
      );
      if (!response.ok) {
        let message = `Report download failed (${response.status}).`;
        try {
          const data = await response.json();
          if (typeof data.detail === "string") message = data.detail;
        } catch {
          /* Do not render a proxy HTML error. */
        }
        throw new Error(message);
      }
      const blob = await response.blob(),
        url = URL.createObjectURL(blob),
        anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `compatibility-${runId}.${format}`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <div className="report-actions">
        {(["json", "html"] as const).map((format) => (
          <a
            key={format}
            className="button secondary"
            href={`/api/compatibility-runs/${runId}/report?format=${format}`}
            download
            aria-disabled={!!busy}
            onClick={(e) => {
              e.preventDefault();
              void download(format);
            }}
          >
            <Download size={14} />
            {busy === format
              ? "Preparing…"
              : `Download ${format.toUpperCase()}`}
          </a>
        ))}
        <span>{engineVersion}</span>
      </div>
      {busy && <p role="status">Preparing the saved report…</p>}
      {error && (
        <div className="error-box" role="alert">
          {error} Try downloading again after resolving the issue.
        </div>
      )}
    </>
  );
}

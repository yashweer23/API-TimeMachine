import type { ReplaySession } from "../../types/replay";
export function SessionStatus({ status }: { status: string }) {
  return (
    <span className={`session-status session-${status}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}
export function ReplaySummary({ session }: { session: ReplaySession }) {
  return (
    <section className="panel replay-summary" aria-label="Replay summary">
      <div className="summary-title">
        <div>
          <span className="eyebrow">EXECUTION SUMMARY</span>
          <h2>{session.name}</h2>
          <code>{session.target_base_url}</code>
        </div>
        <SessionStatus status={session.status} />
      </div>
      <div className="summary-metrics">
        {[
          [
            "Finalized",
            `${session.completed_requests} / ${session.total_requests}`,
          ],
          ["HTTP responses", session.http_responses],
          ["Transport failures", session.failed_requests],
          [
            "Other issues",
            session.error_requests -
              session.failed_requests -
              session.skipped_requests,
          ],
          ["Not executed", session.skipped_requests],
          ["Duration", `${(session.duration_ms / 1000).toFixed(2)} s`],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="summary-time">
        <span>Started {new Date(session.started_at).toLocaleString()}</span>
        <span>
          {session.completed_at
            ? `Finished ${new Date(session.completed_at).toLocaleString()}`
            : "Execution is still in progress."}
        </span>
      </div>
    </section>
  );
}

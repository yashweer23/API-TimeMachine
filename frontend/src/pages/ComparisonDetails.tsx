import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { RefreshCw } from "lucide-react";
import type {
  ComparisonDetail,
  Difference,
  RulesSettings,
} from "../types/comparison";
import type { ReplayResult } from "../types/replay";
import { comparisonApi } from "../services/comparisonApi";
import { replayApi } from "../services/replayApi";
import { errorMessage } from "../services/api";
import { DifferenceExplorer } from "../components/comparison/DifferenceExplorer";
import { JsonDiffViewer } from "../components/comparison/JsonDiffViewer";
import { RulesPanel } from "../components/comparison/RulesPanel";
export function ComparisonDetails({
  onProject,
}: {
  onProject: (id: string) => void;
}) {
  const { id } = useParams(),
    navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const differenceId = searchParams.get("difference");
  const [comparison, setComparison] = useState<ComparisonDetail | null>(null),
    [result, setResult] = useState<ReplayResult | null>(null),
    [settings, setSettings] = useState<RulesSettings | null>(null),
    [selected, setSelected] = useState<Difference | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setComparison(null);
    setResult(null);
    setSettings(null);
    setError("");
    comparisonApi
      .detail(id!)
      .then(async (data) => {
        if (!live) return;
        setComparison(data);
        setSelected(
          data.differences.find((d) => d.id === differenceId) ||
            data.differences[0] ||
            null,
        );
        onProject(data.project_id);
        const [source, rules] = await Promise.all([
          replayApi.result(data.replay_result_id),
          comparisonApi.settings(data.project_id),
        ]);
        if (live) {
          setResult(source);
          setSettings(rules);
        }
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [id, revision, onProject, differenceId]);
  const recalculate = async () => {
    if (!comparison) return;
    setBusy(true);
    setError("");
    try {
      const next = await comparisonApi.compare(comparison.replay_result_id);
      if (next.id !== id) navigate(`/comparisons/${next.id}`);
      else {
        setComparison(next);
        setSelected(next.differences[0] || null);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const current =
    comparison && settings
      ? comparison.rules_hash === settings.rules_hash &&
        comparison.algorithm_version === "pointer-v1"
      : comparison?.is_current;
  return (
    <>
      <div className="replay-navigation">
        {comparison && (
          <Link
            className="text-button"
            to={`/compatibility?project=${comparison.project_id}&session=${comparison.replay_session_id}`}
          >
            Assess session compatibility
          </Link>
        )}
        <Link
          to={
            comparison
              ? `/comparisons?project=${comparison.project_id}&session=${comparison.replay_session_id}`
              : "/comparisons"
          }
          className="text-button"
        >
          Session comparisons
        </Link>
        {comparison && (
          <Link
            className="text-button"
            to={`/replay/sessions/${comparison.replay_session_id}?result=${comparison.replay_result_id}`}
          >
            Open replay execution
          </Link>
        )}
      </div>
      <div className="page-intro">
        <div>
          <h1>Response comparison</h1>
          <p>
            {comparison
              ? `${comparison.request_method} ${comparison.endpoint_path} · ${comparison.recording_name}`
              : "Loading saved comparison…"}
          </p>
        </div>
        <button
          className="button primary"
          disabled={!settings || busy}
          onClick={() => void recalculate()}
        >
          <RefreshCw size={14} />
          {busy ? "Recalculating…" : "Recalculate with current rules"}
        </button>
      </div>
      {error && (
        <div className="error-box mb-5" role="alert">
          {error}
          <button
            className="text-button"
            onClick={() => setRevision((v) => v + 1)}
          >
            Retry
          </button>
        </div>
      )}
      {!comparison && !error ? (
        <div className="empty-state" role="status">
          Loading comparison…
        </div>
      ) : (
        comparison && (
          <>
            <section
              className="panel comparison-detail-summary"
              aria-label="Comparison summary"
            >
              <div>
                <span
                  className={`comparison-status state-${comparison.comparison_status}`}
                >
                  {comparison.comparison_status}
                </span>
                <strong>
                  {comparison.total_differences} detected differences
                </strong>
              </div>
              <p>
                {comparison.session_name} ·{" "}
                {new Date(comparison.compared_at).toLocaleString()} ·{" "}
                {comparison.algorithm_version}
              </p>
              <div className="comparison-counts">
                {Object.entries(comparison.counts)
                  .filter(([, n]) => n > 0)
                  .map(([kind, count]) => (
                    <span key={kind}>
                      {kind.replaceAll("_", " ")} <strong>{count}</strong>
                    </span>
                  ))}
              </div>
            </section>
            {!current && (
              <p className="warning-note" role="status">
                This historical comparison uses older settings. Recalculate to
                use current project rules; this result stays available in
                history.
              </p>
            )}
            {comparison.notes.map((note) => (
              <p className="warning-note" key={note}>
                {note}
              </p>
            ))}
            <details className="effective-rules">
              <summary>Rules used for this comparison</summary>
              <pre>{JSON.stringify(comparison.effective_rules, null, 2)}</pre>
            </details>
            <DifferenceExplorer
              key={comparison.id}
              comparison={comparison}
              selected={selected?.id || null}
              onSelect={setSelected}
            />
            {result && (
              <JsonDiffViewer
                comparison={comparison}
                result={result}
                selected={selected}
                onSelect={setSelected}
              />
            )}
            {settings && (
              <RulesPanel
                key={settings.rules_hash}
                settings={settings}
                onSaved={setSettings}
              />
            )}
          </>
        )
      )}
    </>
  );
}

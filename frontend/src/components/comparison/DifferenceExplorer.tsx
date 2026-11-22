import { useEffect, useState } from "react";
import type {
  ComparisonDetail,
  Difference,
  DifferenceValues,
} from "../../types/comparison";
import { changeLabels } from "../../types/comparison";
import { comparisonApi } from "../../services/comparisonApi";
import { errorMessage } from "../../services/api";
import { CodeView } from "../CodeView";
export function DifferenceExplorer({
  comparison,
  onSelect,
  selected,
}: {
  comparison: ComparisonDetail;
  onSelect: (d: Difference) => void;
  selected: string | null;
}) {
  const [filter, setFilter] = useState("all"),
    [search, setSearch] = useState(""),
    [expanded, setExpanded] = useState<string | null>(null);
  const rows = comparison.differences.filter(
    (d) =>
      (filter === "all" ||
        d.change_type === filter ||
        (filter === "headers" && d.scope === "headers")) &&
      d.path.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <section
      className="panel difference-explorer"
      aria-label="Difference explorer"
    >
      <div className="section-heading">
        <h2>Difference explorer</h2>
        <span>
          {rows.length} / {comparison.total_differences} shown
        </span>
      </div>
      <div className="difference-filters">
        <label>
          Change type
          <select
            aria-label="Filter changes"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All changes</option>
            <option value="headers">All header changes</option>
            {Object.entries(changeLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Search paths
          <input
            aria-label="Search difference paths"
            placeholder="/profile/city"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      {!rows.length ? (
        <div className="empty-state">
          <h3>
            {comparison.total_differences
              ? "No changes match these filters"
              : comparison.comparison_status === "identical"
                ? "No differences under these rules"
                : "No confirmed differences available"}
          </h3>
          <p>
            {comparison.comparison_status === "identical"
              ? "The available responses match under the saved comparison settings."
              : "Inspect the comparison notes and execution details for context."}
          </p>
        </div>
      ) : (
        <div className="difference-rows">
          <div className="difference-table-heading">
            <span>PATH / CHANGE</span>
            <span>ORIGINAL</span>
            <span>REPLAYED</span>
          </div>
          {rows.map((d) => (
            <div
              key={d.id}
              className={`difference-entry ${selected === d.id ? "active" : ""}`}
            >
              <button
                className={`difference-row diff-${d.change_type}`}
                aria-expanded={expanded === d.id}
                aria-label={`Inspect ${d.scope} ${d.path || "(root)"} ${changeLabels[d.change_type]}`}
                onClick={() => {
                  onSelect(d);
                  setExpanded(expanded === d.id ? null : d.id);
                }}
              >
                <span>
                  <code>{d.path || "(root)"}</code>
                  <small>
                    {d.scope} · {changeLabels[d.change_type]}
                  </small>
                </span>
                <span className={!d.old_present ? "missing-value" : ""}>
                  {d.old_preview}
                </span>
                <span className={!d.new_present ? "missing-value" : ""}>
                  {d.new_preview}
                </span>
              </button>
              {expanded === d.id && (
                <ExpandedValues comparison={comparison.id} difference={d} />
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
function ExpandedValues({
  comparison,
  difference: d,
}: {
  comparison: string;
  difference: Difference;
}) {
  const [values, setValues] = useState<DifferenceValues | null>(
      !d.old_value_truncated && !d.new_value_truncated ? d : null,
    ),
    [error, setError] = useState("");
  useEffect(() => {
    if (!d.old_value_truncated && !d.new_value_truncated) return;
    let live = true;
    comparisonApi
      .values(comparison, d.id)
      .then((v) => {
        if (live) setValues(v);
      })
      .catch((e) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [comparison, d]);
  return (
    <div className="difference-expanded">
      {error ? (
        <p role="alert" className="error-box">
          {error}
        </p>
      ) : !values ? (
        <p role="status">Loading complete values…</p>
      ) : (
        <div className="expanded-values">
          {(["old", "new"] as const).map((side) => (
            <div key={side}>
              <h4>
                {side === "old" ? "Original" : "Replayed"} · {d[`${side}_type`]}
              </h4>
              {values[`${side}_present`] ? (
                <CodeView value={values[`${side}_value`]} />
              ) : (
                <p className="missing-value">Missing (not JSON null)</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

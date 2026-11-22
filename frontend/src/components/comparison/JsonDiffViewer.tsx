import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Copy } from "lucide-react";
import type { Json } from "../../types";
import type { ReplayResult } from "../../types/replay";
import type { ComparisonDetail, Difference } from "../../types/comparison";
import { changeLabels, pointerChild } from "../../types/comparison";
import { CodeView } from "../CodeView";
export function JsonDiffViewer({
  comparison,
  result,
  selected,
  onSelect,
}: {
  comparison: ComparisonDetail;
  result: ReplayResult;
  selected: Difference | null;
  onSelect: (d: Difference) => void;
}) {
  const [scope, setScope] = useState<"body" | "headers" | "status">("body"),
    [sync, setSync] = useState(true),
    [copyState, setCopyState] = useState("");
  const left = useRef<HTMLDivElement>(null),
    right = useRef<HTMLDivElement>(null),
    syncing = useRef(false);
  useEffect(() => {
    if (selected) setScope(selected.scope);
  }, [selected]);
  useEffect(() => {
    for (const ref of [left, right]) {
      const node = ref.current?.querySelector(
        '[data-current="true"]',
      ) as HTMLElement | null;
      node?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    }
  }, [selected, scope]);
  const move = (offset: number) => {
    const n = comparison.differences.length;
    if (n)
      onSelect(
        comparison.differences[
          (Math.max(
            0,
            comparison.differences.findIndex((d) => d.id === selected?.id),
          ) +
            offset +
            n) %
            n
        ],
      );
  };
  const synchronize = (
    source: HTMLDivElement,
    target: HTMLDivElement | null,
  ) => {
    if (!sync || !target || syncing.current) return;
    syncing.current = true;
    const span = source.scrollHeight - source.clientHeight;
    target.scrollTop = span
      ? (source.scrollTop / span) * (target.scrollHeight - target.clientHeight)
      : 0;
    requestAnimationFrame(() => {
      syncing.current = false;
    });
  };
  const original = result.original_recording;
  const headerValues = (headers: Record<string, string | string[]>) =>
    Object.fromEntries(
      Object.entries(headers).map(([key, value]) => [
        key.toLowerCase(),
        Array.isArray(value) ? value : [value],
      ]),
    );
  const bodies: [Json, Json] =
    scope === "headers"
      ? [
          headerValues(original.response_headers),
          headerValues(result.response_headers),
        ]
      : scope === "status"
        ? [
            { status: original.response_status },
            { status: result.response_status },
          ]
        : [original.response_body, result.response_body];
  const copy = async (side: 0 | 1) => {
    try {
      const plain =
        scope === "body" &&
        (side === 0 ? original : result).response_body_kind === "text";
      await navigator.clipboard.writeText(
        plain ? String(bodies[side]) : JSON.stringify(bodies[side], null, 2),
      );
      setCopyState(`${side === 0 ? "Original" : "Replayed"} copied`);
    } catch {
      setCopyState(
        "Clipboard unavailable. Select and copy the displayed text.",
      );
    }
  };
  return (
    <section
      className="panel json-diff-viewer"
      aria-label="Highlighted response comparison"
    >
      <div className="comparison-toolbar">
        <div className="flex gap-5">
          {(["body", "headers", "status"] as const).map((t) => (
            <button
              key={t}
              className={scope === t ? "active" : ""}
              onClick={() => setScope(t)}
            >
              {t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
        <div className="diff-navigation">
          <button
            aria-label="Previous difference"
            disabled={!comparison.differences.length}
            onClick={() => move(-1)}
          >
            <ChevronLeft size={16} />
          </button>
          <span>
            {selected ? selected.ordinal + 1 : 0} /{" "}
            {comparison.total_differences}
          </span>
          <button
            aria-label="Next difference"
            disabled={!comparison.differences.length}
            onClick={() => move(1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
      <div className="diff-legend">
        <span className="diff-field_added">+ Added</span>
        <span className="diff-field_removed">− Removed</span>
        <span className="diff-value_changed">~ Modified</span>
        <span className="diff-type_changed">↔ Type changed</span>
        <label>
          <input
            type="checkbox"
            checked={sync}
            onChange={(e) => setSync(e.target.checked)}
          />{" "}
          Sync scroll
        </label>
      </div>
      <div className="comparison-grid">
        {([0, 1] as const).map((side) => {
          const source = side === 0 ? original : result;
          const kind = source.response_body_kind;
          const relevant = comparison.differences.filter(
            (d) =>
              d.scope === scope && (side === 0 ? d.old_present : d.new_present),
          );
          const root = relevant.find((d) => d.path === "");
          return (
            <article
              key={side}
              className="snapshot-panel"
              aria-label={
                side === 0
                  ? "Original highlighted response"
                  : "Replayed highlighted response"
              }
            >
              <div className="snapshot-heading">
                <h3>
                  {side === 0 ? "Original recording" : "Replayed response"}
                </h3>
                <button
                  className="icon-button"
                  aria-label={
                    side === 0
                      ? "Copy original comparison JSON"
                      : "Copy replayed comparison JSON"
                  }
                  onClick={() => void copy(side)}
                  disabled={
                    scope === "body" && (kind === "omitted" || kind === "empty")
                  }
                >
                  <Copy size={15} />
                </button>
              </div>
              <div className="snapshot-url">
                <code>
                  {side === 0
                    ? original.base_url + original.endpoint_path
                    : result.replay_url}
                </code>
              </div>
              <div className="snapshot-meta">
                <strong>
                  {source.response_status === null
                    ? "No HTTP response"
                    : `HTTP ${source.response_status}`}
                </strong>
                <span>{source.duration_ms.toFixed(0)} ms</span>
              </div>
              {source.execution_error && (
                <div className="error-box m-3">
                  <strong>{source.execution_error.code}</strong>
                  <p>{source.execution_error.message}</p>
                </div>
              )}
              <div
                className="diff-tree-scroll"
                ref={side === 0 ? left : right}
                onScroll={(e) =>
                  synchronize(
                    e.currentTarget,
                    side === 0 ? right.current : left.current,
                  )
                }
              >
                {scope === "body" && kind !== "json" ? (
                  kind === "text" ? (
                    <div className={root ? `diff-${root.change_type}` : ""}>
                      {root && (
                        <span className="diff-marker">
                          {changeLabels[root.change_type]}
                        </span>
                      )}
                      <CodeView value={bodies[side]} plain />
                    </div>
                  ) : (
                    <p className="p-5 muted">
                      {kind === "empty"
                        ? "Empty HTTP body (not JSON null)."
                        : "Body unavailable; no body differences inferred."}
                    </p>
                  )
                ) : (
                  <JsonNode
                    value={bodies[side]}
                    path=""
                    label="(root)"
                    changes={relevant}
                    selected={selected?.scope === scope ? selected : null}
                    depth={0}
                  />
                )}
              </div>
            </article>
          );
        })}
      </div>
      {copyState && (
        <p role="status" className="p-3 text-xs">
          {copyState}
        </p>
      )}
    </section>
  );
}
function JsonNode({
  value,
  path,
  label,
  changes,
  selected,
  depth,
}: {
  value: Json;
  path: string;
  label: string;
  changes: Difference[];
  selected: Difference | null;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(depth < 2),
    [visible, setVisible] = useState(100);
  const container = value !== null && typeof value === "object";
  const entries: [string, Json][] = Array.isArray(value)
    ? value.map((v, i) => [String(i), v])
    : container
      ? Object.keys(value)
          .sort()
          .map((k) => [k, (value as Record<string, Json>)[k]])
      : [];
  const change = changes.find((d) => d.path === path),
    descendant = selected && selected.path.startsWith(path + "/");
  useEffect(() => {
    if (descendant) {
      setExpanded(true);
      const index = entries.findIndex(
        ([key]) =>
          selected!.path === pointerChild(path, key) ||
          selected!.path.startsWith(pointerChild(path, key) + "/"),
      );
      if (index >= 100) setVisible(index + 1);
    }
  }, [selected?.id, path]);
  return (
    <div
      className={`json-node ${change ? `diff-${change.change_type}` : ""}`}
      data-current={
        selected?.id === change?.id && !!change ? "true" : undefined
      }
    >
      <div className="json-node-line">
        {container ? (
          <button
            className="tree-toggle"
            aria-label={`${expanded ? "Collapse" : "Expand"} ${path || "(root)"}`}
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="tree-indent" />
        )}
        <code className="code-key">
          {label === "(root)" ? label : JSON.stringify(label)}
        </code>
        <span className="muted">: </span>
        {container ? (
          <span className="muted">
            {Array.isArray(value)
              ? `[${entries.length} items]`
              : `{${entries.length} fields}`}
          </span>
        ) : (
          <code
            className={
              typeof value === "string"
                ? "code-string"
                : typeof value === "number"
                  ? "code-number"
                  : "code-literal"
            }
          >
            {JSON.stringify(value)}
          </code>
        )}
        {change && (
          <span className="diff-marker">
            {changeLabels[change.change_type]}
          </span>
        )}
      </div>
      {container && expanded && (
        <div className="json-children">
          {entries.slice(0, visible).map(([key, item]) => (
            <JsonNode
              key={key}
              value={item}
              path={pointerChild(path, key)}
              label={key}
              changes={changes}
              selected={selected}
              depth={depth + 1}
            />
          ))}
          {entries.length > visible && (
            <button
              className="text-button"
              onClick={() => setVisible((v) => v + 100)}
            >
              Show 100 more ({entries.length - visible} remaining)
            </button>
          )}
        </div>
      )}
    </div>
  );
}

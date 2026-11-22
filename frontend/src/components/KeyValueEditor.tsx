import { Plus, X } from "lucide-react";
export interface Pair {
  id: number;
  key: string;
  value: string;
}
export function KeyValueEditor({
  label,
  rows,
  onChange,
  disabled,
}: {
  label: string;
  rows: Pair[];
  onChange: (rows: Pair[]) => void;
  disabled?: boolean;
}) {
  const update = (id: number, field: "key" | "value", value: string) =>
    onChange(rows.map((r) => (r.id === id ? { ...r, [field]: value } : r)));
  return (
    <div className="kv-editor">
      <div className="kv-labels">
        <span>KEY</span>
        <span>VALUE</span>
      </div>
      {rows.map((row, index) => (
        <div className="kv-row" key={row.id}>
          <input
            disabled={disabled}
            aria-label={`${label} key ${index + 1}`}
            placeholder="Key"
            value={row.key}
            onChange={(e) => update(row.id, "key", e.target.value)}
          />
          <input
            disabled={disabled}
            aria-label={`${label} value ${index + 1}`}
            placeholder="Value"
            value={row.value}
            onChange={(e) => update(row.id, "value", e.target.value)}
          />
          <button
            type="button"
            className="icon-button"
            disabled={disabled}
            aria-label={`Remove ${label} row ${index + 1}`}
            onClick={() => onChange(rows.filter((r) => r.id !== row.id))}
          >
            <X size={14} />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="text-button mt-3"
        disabled={disabled}
        onClick={() =>
          onChange([...rows, { id: Date.now(), key: "", value: "" }])
        }
      >
        <Plus size={13} />
        Add row
      </button>
    </div>
  );
}
export function pairsToObject(
  rows: Pair[],
  repeated = false,
): Record<string, string | string[]> {
  const result: Record<string, string | string[]> = Object.create(null);
  for (const row of rows) {
    const key = row.key.trim();
    if (!key && row.value) throw new Error("Every value needs a key.");
    if (!key) continue;
    if (key in result) {
      if (!repeated) throw new Error(`Duplicate header: ${key}`);
      const current = result[key];
      result[key] = [
        ...(Array.isArray(current) ? current : [current]),
        row.value,
      ];
    } else result[key] = row.value;
  }
  return result;
}

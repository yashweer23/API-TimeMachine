import type { Recording } from "../types";
import type {
  ReplayConfig,
  ReplayDraft,
  ReplayOverride,
} from "../types/replay";
import { parseJsonInput as parse } from "./jsonInput";
export function prepareReplay(
  records: Recording[],
  drafts: Record<string, ReplayDraft>,
  headers: Record<string, string>,
  target: string,
  config: ReplayConfig,
): Record<string, ReplayOverride> {
  if (!records.length) throw new Error("Select at least one recording.");
  if (records.length > config.max_batch_size)
    throw new Error(`Select at most ${config.max_batch_size} recordings.`);
  let url: URL;
  try {
    url = new URL(target);
  } catch {
    throw new Error("Enter an absolute target base URL.");
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    !config.allowed_target_origins.includes(url.origin)
  )
    throw new Error(
      "Choose an approved target origin without credentials, query parameters, or a fragment.",
    );
  const overrides: Record<string, ReplayOverride> = {};
  for (const record of records) {
    const draft = drafts[record.id],
      override: ReplayOverride = {};
    if (draft?.headers.trim()) {
      const value = parse(draft.headers);
      if (
        !value ||
        Array.isArray(value) ||
        typeof value !== "object" ||
        Object.values(value).some((v) => v !== null && typeof v !== "string")
      )
        throw new Error(
          "Header overrides must be a JSON object of strings or null to remove a header.",
        );
      override.headers = value as Record<string, string | null>;
    }
    if (draft?.query.trim()) {
      const value = parse(draft.query);
      if (
        !value ||
        Array.isArray(value) ||
        typeof value !== "object" ||
        Object.values(value).some(
          (v) =>
            typeof v !== "string" &&
            !(Array.isArray(v) && v.every((x) => typeof x === "string")),
        )
      )
        throw new Error(
          "Query overrides must map keys to strings or arrays of strings.",
        );
      override.query_parameters = value as Record<string, string | string[]>;
    }
    if (draft?.bodyMode === "replace") override.body = parse(draft.body);
    if (draft?.bodyMode === "omit") override.omit_body = true;
    if (
      (record.request_body_present === null ||
        record.request_body_present === undefined) &&
      record.request_body === null &&
      !override.omit_body &&
      !Object.hasOwn(override, "body")
    )
      throw new Error(
        "A legacy recording has unknown body presence. Choose “No body” or replace it with JSON null.",
      );
    const effectiveHeaders: Record<string, string> = Object.fromEntries(
      Object.entries(record.request_headers).map(([k, v]) => [
        k.toLowerCase(),
        v,
      ]),
    );
    for (const [key, value] of Object.entries(override.headers || {})) {
      if (value === null) delete effectiveHeaders[key.toLowerCase()];
      else effectiveHeaders[key.toLowerCase()] = value;
    }
    for (const [key, value] of Object.entries(headers))
      effectiveHeaders[key.toLowerCase()] = value;
    const effective = {
      headers: effectiveHeaders,
      query: override.query_parameters ?? record.query_parameters,
      body: override.omit_body
        ? null
        : Object.hasOwn(override, "body")
          ? override.body
          : record.request_body,
      path: record.endpoint_path,
    };
    if (JSON.stringify(effective).includes("[REDACTED]"))
      throw new Error(
        "Masked values remain. Supply temporary headers or replace/remove masked query and body values.",
      );
    if (Object.keys(override).length) overrides[record.id] = override;
  }
  return overrides;
}

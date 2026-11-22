import type { Json } from "../types";
export function parseJsonInput(text: string, label = "Override JSON"): Json {
  try {
    return JSON.parse(text, (_key: string, value: Json) => {
      if (
        typeof value === "number" &&
        (!Number.isFinite(value) ||
          (Number.isInteger(value) && !Number.isSafeInteger(value)))
      )
        throw new Error("Unsafe numeric value");
      return value;
    }) as Json;
  } catch {
    throw new Error(
      `${label} is not valid JSON or contains a number outside the editor’s safe range.`,
    );
  }
}

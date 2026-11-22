import type { Json } from "../types";
export function CodeView({
  value,
  plain = false,
}: {
  value: Json | object;
  plain?: boolean;
}) {
  const text =
    plain && typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const tokens = plain
    ? [text]
    : text.split(
        /("(?:\\.|[^"\\])*"\s*:|"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)/gi,
      );
  return (
    <pre className="code-view" tabIndex={0}>
      <code>
        {tokens.map((token, i) => (
          <span
            key={i}
            className={
              plain
                ? ""
                : /^".*:\s*$/.test(token)
                  ? "code-key"
                  : /^"/.test(token)
                    ? "code-string"
                    : /^(true|false|null)$/.test(token)
                      ? "code-literal"
                      : /^-?\d/.test(token)
                        ? "code-number"
                        : ""
            }
          >
            {token}
          </span>
        ))}
      </code>
    </pre>
  );
}

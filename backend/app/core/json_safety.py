"""Keep captured values compatible with JSONB and bounded recursive redaction."""

import math
from typing import Any


def validate_json_value(value: Any) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("JSON nesting exceeds the supported depth of 64.")
        if isinstance(item, dict):
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite.")
        elif isinstance(item, str):
            if "\x00" in item or any(0xD800 <= ord(char) <= 0xDFFF for char in item):
                raise ValueError(
                    "NUL characters and unpaired Unicode surrogates cannot be stored in JSONB."
                )

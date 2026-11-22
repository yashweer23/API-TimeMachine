import re
import json
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "credential",
    "privatekey",
)
TEXT_SECRET = re.compile(
    r"(?i)((?:api[-_]?key|access[-_]?token|refresh[-_]?token|token|password|passwd|secret|authorization|cookie|credential)[\w-]*[\s\"\']*[:=]\s*[\"\']?)([^\s\"\'&,;}]+)"
)
BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")


class Redactor:
    def __init__(self, extra_fields: list[str] | None = None):
        self.extra_fields = {self.normalize(x) for x in (extra_fields or [])}
        self.secrets: set[str] = set()
        self.temporary_secrets: set[str] = set()
        self.temporary_scalars: set[tuple[str, str]] = set()

    @staticmethod
    def normalize(key: str) -> str:
        return re.sub(r"[^a-z0-9]", "", key.lower())

    def sensitive(self, key: str) -> bool:
        key = self.normalize(key)
        return any(word in key for word in SENSITIVE) or key in self.extra_fields

    def collect(self, value: Any, sensitive: bool = False) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                self.collect(item, sensitive or self.sensitive(key))
        elif isinstance(value, list):
            for item in value:
                self.collect(item, sensitive)
        elif sensitive and isinstance(value, str) and value:
            self.secrets.add(value)
            if value.lower().startswith(("bearer ", "basic ")):
                self.secrets.add(value.split(" ", 1)[1])
            if "=" in value:  # cookie pairs and other key=value credentials
                for part in value.split(";"):
                    if "=" in part and part.split("=", 1)[1].strip():
                        self.secrets.add(part.split("=", 1)[1].strip())

    def collect_temporary(self, value: Any) -> None:
        """Explicit replay inputs are transient, including nonstandard credential names."""
        self.collect(value, sensitive=True)
        self.temporary_secrets.update(self.secrets)
        if isinstance(value, dict):
            for item in value.values():
                self.collect_temporary(item)
        elif isinstance(value, list):
            for item in value:
                self.collect_temporary(item)
        elif value is not None and not isinstance(value, str):
            self.temporary_scalars.add((type(value).__name__, json.dumps(value)))

    def text(self, value: str) -> str:
        if value == REDACTED:
            return value
        secrets = [
            s
            for s in self.secrets
            if len(s) >= 4 or s in self.temporary_secrets or value == s
        ]
        if secrets:
            pattern = re.compile(
                "|".join(re.escape(s) for s in sorted(secrets, key=len, reverse=True))
            )
            value = REDACTED.join(
                pattern.sub(lambda _: REDACTED, part) for part in value.split(REDACTED)
            )
        value = BEARER.sub(lambda m: m.group(1) + " " + REDACTED, value)
        return TEXT_SECRET.sub(lambda m: m.group(1) + REDACTED, value)

    def clean(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                (self.text(key) if self.temporary_secrets else key): REDACTED
                if self.sensitive(key)
                else self.clean(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        if (
            value is not None
            and (type(value).__name__, json.dumps(value)) in self.temporary_scalars
        ):
            return REDACTED
        return self.text(value) if isinstance(value, str) else value

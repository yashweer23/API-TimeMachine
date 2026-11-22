"""Exact-origin allowlisting, DNS validation, and connection-IP pinning."""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

import httpx

from app.core.config import Settings


class TargetRejected(ValueError):
    pass


def normalize_base_url(value: str) -> str:
    if any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise TargetRejected("Base URL must not contain whitespace or backslashes.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TargetRejected("Use an absolute http:// or https:// base URL.")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise TargetRejected(
            "Base URLs cannot contain credentials, queries, or fragments."
        )
    try:
        url = httpx.URL(value)
        _ = parsed.port
    except (ValueError, httpx.InvalidURL) as exc:
        raise TargetRejected("Invalid base URL or port.") from exc
    if parsed.port == 0 or "%" in parsed.netloc:
        raise TargetRejected("Invalid target host or port.")
    return str(url).rstrip("/")


def origin(value: str) -> str:
    url = httpx.URL(normalize_base_url(value))
    return str(url.copy_with(path="", query=None, fragment=None)).rstrip("/")


def validate_path(value: str) -> str:
    decoded = value
    for _ in range(3):
        decoded = unquote(decoded)
    if (
        not value.startswith("/")
        or decoded.startswith("//")
        or "\\" in decoded
        or "?" in value
        or "#" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
        or any(p in {".", ".."} for p in decoded.split("/"))
    ):
        raise ValueError(
            "Use a relative path starting with one /. Put query values in the parameters editor; traversal is not allowed."
        )
    return value


@dataclass(frozen=True)
class Destination:
    url: httpx.URL
    host_header: str
    tls_hostname: str


class TargetPolicy:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.allowed = {
            origin(x) for x in settings.csv(settings.allowed_target_origins)
        }
        self.private = {origin(x) for x in settings.csv(settings.dev_private_origins)}
        self.networks = [
            ipaddress.ip_network(x) for x in settings.csv(settings.dev_private_cidrs)
        ]

    def check_origin(self, base_url: str) -> str:
        normalized = normalize_base_url(base_url)
        if origin(normalized) not in self.allowed:
            raise TargetRejected(
                "Target origin is not allowlisted. Add its exact scheme, hostname, and port to ALLOWED_TARGET_ORIGINS."
            )
        return normalized

    async def resolve(self, hostname: str, port: int) -> list[str]:
        loop = asyncio.get_running_loop()
        entries = await asyncio.wait_for(
            loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM),
            timeout=self.settings.connect_timeout_seconds,
        )
        return list(dict.fromkeys(entry[4][0] for entry in entries))

    async def destination(self, base_url: str, endpoint: str) -> Destination:
        base_url = self.check_origin(base_url)
        validate_path(endpoint)
        url = httpx.URL(base_url + endpoint)
        addresses = await self.resolve(
            url.host, url.port or (443 if url.scheme == "https" else 80)
        )
        if not addresses:
            raise OSError("No addresses returned by DNS")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            mapped = getattr(ip, "ipv4_mapped", None)
            ip = mapped or ip
            # Metadata/link-local, multicast, unspecified and reserved ranges are never allowed.
            denied = (
                ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or ip.is_reserved
            )
            explicitly_private = origin(base_url) in self.private and any(
                ip in network for network in self.networks
            )
            if denied or not (ip.is_global or explicitly_private):
                raise TargetRejected(
                    "Target resolves to a blocked IP address. Private targets require an explicit development origin and CIDR."
                )
        # The connection uses this IP, avoiding a second DNS lookup / rebinding race.
        return Destination(
            url.copy_with(host=addresses[0]), url.netloc.decode("ascii"), url.host
        )

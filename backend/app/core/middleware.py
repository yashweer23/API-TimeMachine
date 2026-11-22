from starlette.responses import JSONResponse


class RequestGuard:
    """Bound incoming payloads before JSON parsing; reject cross-origin writes."""

    def __init__(self, app, max_bytes: int, origins: list[str]):
        self.app, self.max_bytes, self.origins = app, max_bytes, set(origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode("latin1")
        if origin and origin not in self.origins:
            return await JSONResponse(
                {"detail": "Origin is not allowed."}, status_code=403
            )(scope, receive, send)
        if (
            headers.get(b"content-type", b"").split(b";", 1)[0].strip()
            != b"application/json"
        ):
            return await JSONResponse(
                {"detail": "Use Content-Type: application/json."}, status_code=415
            )(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                return await JSONResponse(
                    {"detail": "Request payload exceeds the configured limit."},
                    status_code=413,
                )(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, bounded_receive, send)

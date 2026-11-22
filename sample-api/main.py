"""Deterministic, independently runnable v1 and v2 replay fixtures."""

import asyncio
import os
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse

VERSION = os.getenv("API_VERSION", "v1")
if VERSION not in {"v1", "v2"}:
    raise ValueError("API_VERSION must be v1 or v2")
app = FastAPI(
    title=f"TimeMachine Sample API {VERSION}",
    version="2.0.0" if VERSION == "v2" else "1.0.0",
)
USERS = [
    {
        "id": 1,
        "name": "Maya Chen",
        "email": "maya@example.test",
        "role": "admin",
        "active": True,
    },
    {
        "id": 2,
        "name": "Arjun Rao",
        "email": "arjun@example.test",
        "role": "developer",
        "active": True,
    },
    {
        "id": 3,
        "name": "Lena Ortiz",
        "email": "lena@example.test",
        "role": "viewer",
        "active": False,
    },
]
PRODUCTS = [
    {
        "id": "prod_001",
        "name": "Workspace",
        "price": 29.0,
        "currency": "USD",
        "in_stock": True,
    },
    {
        "id": "prod_002",
        "name": "Team seat",
        "price": 12.0,
        "currency": "USD",
        "in_stock": True,
    },
]


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


def serialize_user(user):
    if VERSION == "v1":
        return dict(user)
    return {
        "id": str(user["id"]),
        "full_name": user["name"],
        "email": user["email"],
        "account_status": "active" if user["active"] else "suspended",
    }


@app.get("/users")
def users(role: str | None = None):
    data = [u for u in USERS if role is None or u["role"] == role]
    return {
        "data": [serialize_user(u) for u in data],
        "total": len(data),
        "version": VERSION,
    }


@app.get("/users/{user_id}")
def user(user_id: int):
    for u in USERS:
        if u["id"] == user_id:
            return {"data": serialize_user(u), "version": VERSION}
    raise HTTPException(404, "User not found")


@app.api_route("/echo", methods=["POST", "PUT", "PATCH", "DELETE"])
async def echo(request: Request, response: Response):
    if VERSION == "v2" and request.method == "POST":
        response.status_code = 201
    raw = await request.body()
    body = await request.json() if raw else None
    return {
        "method": request.method,
        "body": body,
        "query": dict(request.query_params),
        "version": VERSION,
    }


@app.get("/products")
def products():
    data = (
        PRODUCTS
        if VERSION == "v1"
        else [
            {
                "id": p["id"],
                "name": p["name"],
                "price": f"{p['price']:.2f}",
                "currency": p["currency"],
                "availability": "available",
            }
            for p in PRODUCTS
        ]
    )
    return {"data": data, "total": len(data), "version": VERSION}


@app.get("/text", response_class=PlainTextResponse)
def text():
    return f"API TimeMachine sample API · {VERSION}\nDeterministic plain-text response."


@app.get("/slow")
async def slow(seconds: float = Query(12, ge=0, le=30)):
    await asyncio.sleep(seconds)
    return {"waited_seconds": seconds}


@app.get("/redirect")
def redirect():
    return RedirectResponse("/users", status_code=302)


# Focused deterministic fixtures: none embeds a generic version marker.
# Each case isolates its expected difference, apart from HTTP Content-Length.
@app.get("/regression/{case}")
def regression(case: str, response: Response):
    v2 = VERSION == "v2"
    if case == "unchanged":
        return {"id": 1, "name": "Maya"}
    if case == "added":
        return {"id": 1, **({"enabled": True} if v2 else {})}
    if case == "removed":
        return {"id": 1, **({} if v2 else {"legacy": None})}
    if case == "value":
        return {"city": "Bangalore" if v2 else "Hyderabad"}
    if case == "type":
        return {"age": "24" if v2 else 24}
    if case == "nested":
        return {"profile": {"address": {"city": "Pune" if v2 else "Goa"}}}
    if case == "array":
        return {"roles": ["user", "admin" if v2 else "editor"]}
    if case == "status":
        response.status_code = 201 if v2 else 200
        return {"ok": True}
    if case == "headers":
        response.headers["X-Contract"] = "next" if v2 else "base"
        response.headers.append("X-Feature", "capture")
        response.headers.append("X-Feature", "compare" if v2 else "replay")
        return {"ok": True}
    if case == "timestamp":
        return {
            "id": 1,
            "generated_at": "2026-11-11T10:00:00Z" if v2 else "2026-11-10T10:00:00Z",
        }
    if case == "text":
        return PlainTextResponse("hello\nnew line\n" if v2 else "hello\nold line\n")
    if case == "empty":
        return Response(status_code=204)
    if case == "unordered":
        return {"roles": ["editor", "user"] if v2 else ["user", "editor"]}
    raise HTTPException(404, "Unknown regression fixture")


@app.get("/compatibility/{case}")
async def compatibility(case: str, response: Response):
    """Ten focused Phase 4 cases; transport intentionally exceeds capture timeout."""
    v2 = VERSION == "v2"
    if case == "unchanged":
        return {"id": 1, "name": "Maya"}
    if case == "required-removed":
        return {"name": "Maya", **({} if v2 else {"id": 1})}
    if case == "type":
        return {"age": "24" if v2 else 24}
    if case == "added":
        return {"id": 1, **({"enabled": True} if v2 else {})}
    if case == "value":
        return {"city": "Bangalore" if v2 else "Hyderabad"}
    if case == "status":
        response.status_code = 201 if v2 else 200
        return {"ok": True}
    if case == "error":
        response.status_code = 500 if v2 else 200
        return {"message": "Fixture response"}
    if case == "header":
        if not v2:
            response.headers["X-Contract"] = "v1"
        return {"ok": True}
    if case == "timestamp":
        return {
            "generated_at": "2026-11-18T10:00:00Z" if v2 else "2026-11-17T10:00:00Z"
        }
    if case == "transport":
        if v2:
            await asyncio.sleep(25)
        return {"ok": True}
    raise HTTPException(404, "Unknown compatibility fixture")

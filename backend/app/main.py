from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy.orm import Session
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.api.comparison_routes import router as comparison_router
from app.api.compatibility_routes import router as compatibility_router
from app.api.replay_routes import router as replay_router
from app.db.session import get_engine
from app.services.replay_service import ReplayService, recover_interrupted_sessions
from app.core.config import Settings, get_settings
from app.core.middleware import RequestGuard
from app.core.security import TargetPolicy, TargetRejected
from app.services.recorder import Recorder


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        if settings.recover_replays_on_startup:
            with Session(get_engine()) as db:
                recover_interrupted_sessions(db)
        yield

    app = FastAPI(
        title="API TimeMachine",
        version="1.0.0",
        description="Record and explicitly replay APIs with sanitized, persistent history. Local development only.",
        lifespan=lifespan,
    )
    app.state.policy = TargetPolicy(settings)
    app.state.recorder = Recorder(settings, app.state.policy)
    app.state.replays = ReplayService(settings, app.state.policy)
    app.include_router(router)
    app.include_router(replay_router)
    app.include_router(comparison_router)
    app.include_router(compatibility_router)
    app.add_middleware(
        RequestGuard,
        max_bytes=settings.max_request_bytes,
        origins=settings.csv(settings.cors_origins),
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=settings.csv(settings.trusted_hosts)
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.csv(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH", "PUT"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(TargetRejected)
    async def blocked(request: Request, exc: TargetRejected):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        # Pydantic's default errors echo input values (including tokens); only return locations and messages.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {
                        "loc": e["loc"][:1],
                        "msg": "Invalid replay input; check IDs, target URL, headers, and overrides."
                        if "replay" in request.url.path
                        else e["msg"],
                        "type": e["type"],
                    }
                    for e in exc.errors()
                ]
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database unavailable. If this followed Send or Replay, the target may have received the request but the recording could not be saved. Check the database before retrying."
            },
        )

    return app


app = create_app()

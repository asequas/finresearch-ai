from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes.meta import router as meta_router
from backend.api.routes.costs import router as costs_router
from backend.api.routes.research import companies_router, router as research_router
from backend.core.config import settings
from backend.services.errors import (
    BadRequestError,
    ConflictError,
    InvalidStateError,
    LimitReachedError,
    NotFoundError,
    UpstreamBusyError,
)


app = FastAPI(
    title="FinResearch AI",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key"],
    expose_headers=["Location"],
)


@app.exception_handler(NotFoundError)
def not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
@app.exception_handler(InvalidStateError)
def conflict(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(BadRequestError)
def bad_request(_request: Request, exc: BadRequestError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})


@app.exception_handler(LimitReachedError)
def limit_reached(_request: Request, exc: LimitReachedError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": str(exc)})


@app.exception_handler(UpstreamBusyError)
def upstream_busy(_request: Request, exc: UpstreamBusyError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}, headers={"Retry-After": "60"}
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(research_router)
app.include_router(companies_router)
app.include_router(meta_router)
app.include_router(costs_router)

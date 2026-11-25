import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import ROOT_DIR
from app.keitaro.client import KeitaroBadRequestError, KeitaroError, KeitaroNotFoundError
from app.services.exceptions import (
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)


def _configure_logging() -> None:
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


_configure_logging()


@asynccontextmanager
async def _lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    yield
    client = getattr(app_instance.state, "keitaro_client", None)
    if client is not None:
        client.close()


app = FastAPI(title="Keitaro Wrapper API", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _json_error(status_code: int, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


@app.exception_handler(NotFoundError)
async def _handle_not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
    return _json_error(404, exc)


@app.exception_handler(KeitaroNotFoundError)
async def _handle_keitaro_not_found(_request: Request, exc: KeitaroNotFoundError) -> JSONResponse:
    return _json_error(404, exc)


@app.exception_handler(ConflictError)
async def _handle_conflict(_request: Request, exc: ConflictError) -> JSONResponse:
    return _json_error(409, exc)


@app.exception_handler(ValidationError)
async def _handle_validation(_request: Request, exc: ValidationError) -> JSONResponse:
    return _json_error(422, exc)


@app.exception_handler(ValueError)
async def _handle_value_error(_request: Request, exc: ValueError) -> JSONResponse:
    return _json_error(422, exc)


@app.exception_handler(KeitaroBadRequestError)
async def _handle_keitaro_bad_request(
    _request: Request,
    exc: KeitaroBadRequestError,
) -> JSONResponse:
    return _json_error(400, exc)


@app.exception_handler(ExternalServiceError)
async def _handle_external_error(_request: Request, exc: ExternalServiceError) -> JSONResponse:
    return _json_error(502, exc)


@app.exception_handler(KeitaroError)
async def _handle_keitaro_error(_request: Request, exc: KeitaroError) -> JSONResponse:
    return _json_error(502, exc)


app.include_router(api_router)

FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
if FRONTEND_DIST_DIR.is_dir():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = FRONTEND_DIST_DIR / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")

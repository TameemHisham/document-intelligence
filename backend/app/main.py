import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image

from app.config import get_settings
from app.db import init_db
from app.qa import AIUnavailable
from app.usage import LimitExceeded
from app.routers import auth, documents, library

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Image.MAX_IMAGE_PIXELS = get_settings().max_image_pixels  # decompression-bomb guard
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Document Intelligence API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().frontend_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.exception_handler(LimitExceeded)
    async def _limit(_req: Request, exc: LimitExceeded):
        return JSONResponse({"detail": str(exc)}, status_code=429)

    @app.exception_handler(AIUnavailable)
    async def _ai(_req: Request, exc: AIUnavailable):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(Exception)
    async def _unhandled(req: Request, exc: Exception):
        log.exception("unhandled error on %s %s", req.method, req.url.path)
        return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)

    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(library.router)

    @app.get("/health")
    def health():
        s = get_settings()
        return {
            "ok": True,
            "storage": s.storage_backend,
            "ocr": s.ocr_backend,
            "claude": bool(s.anthropic_api_key),
            "fake_models": s.fake_models,
        }

    return app


app = create_app()

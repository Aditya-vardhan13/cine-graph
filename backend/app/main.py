from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.core.config import get_settings
from app.migrations import run_migrations

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    run_migrations()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

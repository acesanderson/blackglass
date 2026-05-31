from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import settings
from .db import init_pool, close_pool
from .observability import install_logging, install_middleware
from .routes import notes, vault_routes, search, sync, observability_routes


install_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="blackglass", version="0.1.0", lifespan=lifespan)
install_middleware(app)
app.include_router(notes.router)
app.include_router(vault_routes.router)
app.include_router(search.router)
app.include_router(sync.router)
app.include_router(observability_routes.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "vault": str(settings.vault_path)}

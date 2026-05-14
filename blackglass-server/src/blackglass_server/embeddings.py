from __future__ import annotations
import httpx
from .config import settings

_MODEL = "nomic-ai/nomic-embed-text-v1.5"


async def embed_text(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.backwater_url}/conduit/embeddings/quick",
            json={"query": text, "model": _MODEL},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


async def embed_batch(texts: list[str], ids: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.backwater_url}/conduit/embeddings",
            json={
                "model": _MODEL,
                "batch": {"ids": ids, "documents": texts, "embeddings": None, "metadatas": {}},
            },
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

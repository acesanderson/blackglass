from __future__ import annotations
import os
import asyncpg
from pgvector.asyncpg import register_vector
from dbclients.discovery.host import get_network_context

_pool: asyncpg.Pool | None = None
_EMBED_DIM = 768


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first")
    return _pool


async def init_pool() -> None:
    global _pool
    ctx = get_network_context()
    _pool = await asyncpg.create_pool(
        host=ctx.preferred_host,
        port=5432,
        database="blackglass",
        user=os.environ.get("POSTGRES_USERNAME", "bianders"),
        password=os.environ["POSTGRES_PASSWORD"],
        init=register_vector,
    )
    await _ensure_schema()


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def _ensure_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS vault_embeddings (
                path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                embedding vector({_EMBED_DIM}),
                indexed_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS vault_embeddings_embedding_idx
            ON vault_embeddings USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)


async def upsert_embedding(path: str, content_hash: str, embedding: list[float]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO vault_embeddings (path, content_hash, embedding, indexed_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (path) DO UPDATE
            SET content_hash = EXCLUDED.content_hash,
                embedding = EXCLUDED.embedding,
                indexed_at = now()
        """, path, content_hash, embedding)


async def get_indexed_hashes() -> dict[str, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT path, content_hash FROM vault_embeddings")
        return {r["path"]: r["content_hash"] for r in rows}


async def semantic_search(query_embedding: list[float], limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT path, 1 - (embedding <=> $1) AS score
            FROM vault_embeddings
            ORDER BY embedding <=> $1
            LIMIT $2
        """, query_embedding, limit)
        return [{"path": r["path"], "score": float(r["score"])} for r in rows]

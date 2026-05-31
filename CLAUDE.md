# Blackglass — Agent Instructions

Blackglass is a FastAPI server + Click CLI that exposes the Obsidian vault over HTTP for agentic access. Target deployment host: Botvinnik (172.16.0.3), port 8083.

Directory: `/Users/bianders/Brian_Code/blackglass` (monorepo with `blackglass-client/`, `blackglass-server/`, `docs/`, `jobs/`)

## Critical: Botvinnik GPU Constraint

Botvinnik has a ~3.6 GiB GPU. `nomic-ai/nomic-embed-text-v1.5` occupies ~2.5 GiB, leaving ~1 GiB for activations. Backwater does not use flash attention — attention activations scale O(L²).

**Hard limits in `blackglass-server/src/blackglass_server/routes/sync.py`:**
- `batch_size = 4`
- `_MAX_EMBED_CHARS = 2000` per document

Even `batch=8` + `trunc=4000` caused OOM after ~10 batches. The vault contains outlier notes up to 2.4 MB (`Work Docs/Archived_Notes.md`).

**If tempted to increase batch_size:** don't. Instead either (a) point blackglass at deepwater on AlphaBlue (bigger GPU), or (b) switch backwater's model to something smaller. Tighter truncation loses semantic content past the cutoff — semantic search recall on long notes suffers.

## Deployment Checklist (HITL required)

1. Push to GitHub: `cd $BC/blackglass-project && git push -u origin main`
2. Clone vault on botvinnik at `~/services/vault`
3. Clone blackglass on botvinnik at `~/services/blackglass`
4. Pre-install dbclients on botvinnik
5. Create `blackglass` database on Caruana: `createdb blackglass`
6. Set env vars on botvinnik: `BLACKGLASS_VAULT_PATH`, `BLACKGLASS_API_KEY`, `POSTGRES_PASSWORD`
7. Create + enable systemd service (see obsidian skill for full unit template)
8. Run initial sync: `POST /vault/sync`
9. Install CLI on Petrosian: `uv pip install -e $BC/blackglass-project/src/blackglass/blackglass-client`

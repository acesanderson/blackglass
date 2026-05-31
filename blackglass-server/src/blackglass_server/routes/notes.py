from __future__ import annotations

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_api_key
from ..config import settings
from ..vault import read_note, write_note, delete_note, note_meta, _resolve
from ..text_utils import split_frontmatter

router = APIRouter(prefix="/vault/notes", dependencies=[Depends(require_api_key)])


class NoteCreate(BaseModel):
    content: str


class NotePatch(BaseModel):
    op: str
    content: str | None = None
    key: str | None = None
    value: str | None = None


# Registered BEFORE the catch-all GET /{path:path}; FastAPI's first-match resolution
# routes /vault/notes/<rel>/meta here. Reordering these decorators silently breaks meta.
@router.get("/{path:path}/meta")
def get_meta(path: str) -> dict:
    try:
        return note_meta(settings.vault_path, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="path escapes vault")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="path is a directory")


@router.get("/{path:path}")
def get_note(path: str) -> dict:
    try:
        return read_note(settings.vault_path, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_note(path: str, body: NoteCreate) -> dict:
    try:
        full = _resolve(settings.vault_path, path)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid path: {path}")
    if full.exists():
        raise HTTPException(status_code=409, detail=f"Note already exists: {path}")
    write_note(settings.vault_path, path, body.content)
    return read_note(settings.vault_path, path)


@router.put("/{path:path}")
def replace_note(path: str, body: NoteCreate) -> dict:
    write_note(settings.vault_path, path, body.content)
    return read_note(settings.vault_path, path)


@router.patch("/{path:path}")
def patch_note(path: str, body: NotePatch) -> dict:
    try:
        note = read_note(settings.vault_path, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")

    if body.op == "append":
        new_content = note["content"].rstrip() + "\n" + (body.content or "")
    elif body.op == "prepend":
        fm, b = split_frontmatter(note["content"])
        fm_block = "---\n" + yaml.dump(fm, default_flow_style=False) + "---\n" if fm else ""
        new_content = fm_block + (body.content or "") + "\n" + b
    elif body.op == "set_frontmatter":
        if body.key is None:
            raise HTTPException(status_code=422, detail="set_frontmatter requires 'key'")
        fm, b = split_frontmatter(note["content"])
        fm[body.key] = body.value
        new_content = "---\n" + yaml.dump(fm, default_flow_style=False) + "---\n" + b
    else:
        raise HTTPException(status_code=422, detail=f"Unknown op: {body.op}")

    write_note(settings.vault_path, path, new_content)
    return read_note(settings.vault_path, path)


@router.delete("/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_route(path: str) -> None:
    try:
        delete_note(settings.vault_path, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")

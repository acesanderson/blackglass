from __future__ import annotations
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from .config import settings

_header = APIKeyHeader(name="X-API-Key")


def require_api_key(key: str = Security(_header)) -> str:
    if key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return key

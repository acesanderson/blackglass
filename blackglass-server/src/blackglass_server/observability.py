from __future__ import annotations
import collections
import logging
import time
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from fastapi import FastAPI, Request, Response


request_id_var: ContextVar[str] = ContextVar("request_id", default="system")


_STANDARD_LOG_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName", "request_id",
})


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 200):
        super().__init__()
        self.capacity = capacity
        self._buffer: collections.deque[logging.LogRecord] = collections.deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.append(record)

    def get_records(self, n: int) -> list[dict]:
        if n <= 0:
            return []
        records = list(self._buffer)[-n:]
        result = []
        for r in records:
            extra = {
                k: v for k, v in r.__dict__.items()
                if k not in _STANDARD_LOG_ATTRS
                and isinstance(v, (str, int, float, bool, type(None)))
            }
            result.append({
                "timestamp": r.created,
                "level": r.levelname,
                "logger": r.name,
                "message": r.getMessage(),
                "request_id": getattr(r, "request_id", None),
                "extra": extra or None,
            })
        return result


ring_buffer = RingBufferHandler(capacity=200)


_started_at: float = time.time()


def started_at() -> float:
    return _started_at


_orig_record_factory = logging.getLogRecordFactory()


def _request_id_record_factory(*args, **kwargs):
    record = _orig_record_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    return record


def install_logging() -> None:
    root = logging.getLogger()
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    if ring_buffer not in root.handlers:
        root.addHandler(ring_buffer)
    logging.setLogRecordFactory(_request_id_record_factory)


_logger = logging.getLogger("blackglass.request")


def install_middleware(app: "FastAPI") -> None:
    @app.middleware("http")
    async def correlation_middleware(request: "Request", call_next: "Callable") -> "Response":
        header_value = request.headers.get("X-Request-ID", "")
        try:
            parsed = uuid.UUID(header_value)
            request_id = header_value if parsed.version == 4 else str(uuid.uuid4())
        except (ValueError, AttributeError):
            request_id = str(uuid.uuid4())

        token = request_id_var.set(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 1)

        _logger.info(
            "request_finished",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        request_id_var.reset(token)
        return response


_last_sync: dict | None = None


def record_sync(payload: dict) -> None:
    global _last_sync
    _last_sync = payload


def last_sync() -> dict | None:
    return _last_sync

from __future__ import annotations
import click
from ..client import request
from ._output import _emit


@click.group()
@click.pass_context
def obs(ctx: click.Context) -> None:
    """Observability: status and logs."""
    ctx.ensure_object(dict)
    ctx.obj.setdefault("pretty", False)


@obs.command("status")
@click.pass_context
def status(ctx: click.Context) -> None:
    """Server status, version, indexed count, last sync."""
    _emit(request("GET", "/status"), ctx.obj["pretty"])


@obs.command("logs-last")
@click.option("-n", "n", type=int, help="Number of entries (1..200, default 50).")
@click.pass_context
def logs_last(ctx: click.Context, n: int | None) -> None:
    """In-memory ring buffer of recent log records."""
    params = {"n": str(n)} if n is not None else None
    _emit(request("GET", "/logs/last", params=params), ctx.obj["pretty"])


@obs.command("logs-journal")
@click.option("-n", "n", type=int, help="Number of lines (1..2000, default 100).")
@click.pass_context
def logs_journal(ctx: click.Context, n: int | None) -> None:
    """systemd journal entries for the blackglass unit."""
    params = {"n": str(n)} if n is not None else None
    _emit(request("GET", "/logs/journal", params=params), ctx.obj["pretty"])

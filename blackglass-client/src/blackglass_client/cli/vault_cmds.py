from __future__ import annotations
import click
from ..client import request
from ._output import _emit
from ._payloads import (
    patch_op_append,
    patch_op_prepend,
    patch_op_set_frontmatter,
    patch_op_replace,
)


@click.group()
@click.pass_context
def vault(ctx: click.Context) -> None:
    """Vault-level operations."""
    ctx.ensure_object(dict)
    ctx.obj.setdefault("pretty", False)


def _parse_fm(ctx: click.Context, param: click.Parameter, values: tuple[str, ...]) -> dict:
    out: dict[str, str] = {}
    for v in values:
        if "=" not in v:
            raise click.BadParameter(f"--fm expects KEY=VALUE, got: {v!r}")
        k, val = v.split("=", 1)
        out[k] = val
    return out


@vault.command("files")
@click.option("--tag", multiple=True, help="Filter to notes tagged with TAG. Repeatable.")
@click.option(
    "--fm",
    "fm_filters",
    multiple=True,
    callback=_parse_fm,
    help="Filter by frontmatter KEY=VALUE. Repeatable.",
)
@click.option("--path-glob", help="POSIX glob to restrict paths.")
@click.option("--limit", type=int, help="Cap result count.")
@click.pass_context
def files(
    ctx: click.Context,
    tag: tuple[str, ...],
    fm_filters: dict[str, str],
    path_glob: str | None,
    limit: int | None,
) -> None:
    """List notes in the vault, optionally filtered."""
    params: list[tuple[str, str]] = []
    for t in tag:
        params.append(("tag", t))
    for k, v in fm_filters.items():
        params.append((f"fm.{k}", v))
    if path_glob is not None:
        params.append(("path_glob", path_glob))
    if limit is not None:
        params.append(("limit", str(limit)))
    _emit(request("GET", "/vault/files", params=params), ctx.obj["pretty"])


@vault.command("tags")
@click.pass_context
def tags(ctx: click.Context) -> None:
    """List all tags with counts."""
    _emit(request("GET", "/vault/tags"), ctx.obj["pretty"])


@vault.command("backlinks")
@click.argument("path")
@click.pass_context
def backlinks(ctx: click.Context, path: str) -> None:
    """List notes that link to PATH."""
    _emit(request("GET", f"/vault/backlinks/{path}"), ctx.obj["pretty"])


@vault.command("sync")
@click.pass_context
def sync(ctx: click.Context) -> None:
    """Git pull and re-index changed notes."""
    _emit(request("POST", "/vault/sync"), ctx.obj["pretty"])


@vault.command("changes")
@click.option("--since", help="Epoch seconds or ISO 8601 timestamp.")
@click.option("--days", type=int, help="Look back N days (1..365).")
@click.option("--limit", type=int, help="Cap returned changes (1..2000, default 200).")
@click.option("--diff-stats", is_flag=True, help="Include per-file diff stats.")
@click.pass_context
def changes(
    ctx: click.Context,
    since: str | None,
    days: int | None,
    limit: int | None,
    diff_stats: bool,
) -> None:
    """List recent vault changes from git history."""
    params: dict[str, str] = {}
    if since is not None:
        params["since"] = since
    if days is not None:
        params["days"] = str(days)
    if limit is not None:
        params["limit"] = str(limit)
    if diff_stats:
        params["include_diff_stats"] = "true"
    _emit(request("GET", "/vault/changes", params=params or None), ctx.obj["pretty"])


@vault.group("periodic")
def periodic():
    """Daily/periodic note operations."""


@periodic.command("list")
@click.pass_context
def periodic_list(ctx: click.Context) -> None:
    """List all periodic (daily) notes."""
    _emit(request("GET", "/vault/periodic"), ctx.obj["pretty"])


@periodic.command("today")
@click.pass_context
def periodic_today(ctx: click.Context) -> None:
    """Get (and ensure) today's daily note."""
    _emit(request("GET", "/vault/periodic/today"), ctx.obj["pretty"])


@periodic.command("yesterday")
@click.pass_context
def periodic_yesterday(ctx: click.Context) -> None:
    """Get (and ensure) yesterday's daily note."""
    _emit(request("GET", "/vault/periodic/yesterday"), ctx.obj["pretty"])


@periodic.command("on")
@click.argument("date_str")
@click.pass_context
def periodic_on(ctx: click.Context, date_str: str) -> None:
    """Get (and ensure) the daily note for DATE_STR (YYYY-MM-DD)."""
    _emit(request("GET", f"/vault/periodic/by-date/{date_str}"), ctx.obj["pretty"])


@periodic.command("append-today")
@click.argument("content")
@click.pass_context
def periodic_append_today(ctx: click.Context, content: str) -> None:
    """Append CONTENT to today's daily note."""
    _emit(
        request("POST", "/vault/periodic/today/append", json={"content": content}),
        ctx.obj["pretty"],
    )


@periodic.group("patch-today")
def patch_today():
    """Patch today's daily note (op subcommands)."""


def _patch_today_send(ctx: click.Context, body: dict) -> None:
    _emit(request("PATCH", "/vault/periodic/today", json=body), ctx.obj["pretty"])


@patch_today.command("append")
@click.argument("content")
@click.pass_context
def patch_today_append(ctx: click.Context, content: str) -> None:
    _patch_today_send(ctx, patch_op_append(content))


@patch_today.command("prepend")
@click.argument("content")
@click.pass_context
def patch_today_prepend(ctx: click.Context, content: str) -> None:
    _patch_today_send(ctx, patch_op_prepend(content))


@patch_today.command("set-frontmatter")
@click.argument("key")
@click.argument("value")
@click.pass_context
def patch_today_set_frontmatter(ctx: click.Context, key: str, value: str) -> None:
    _patch_today_send(ctx, patch_op_set_frontmatter(key, value))


@patch_today.command("replace")
@click.option("--old", required=True)
@click.option("--new", required=True)
@click.option("--replace-all", is_flag=True)
@click.pass_context
def patch_today_replace(ctx: click.Context, old: str, new: str, replace_all: bool) -> None:
    _patch_today_send(ctx, patch_op_replace(old, new, replace_all))

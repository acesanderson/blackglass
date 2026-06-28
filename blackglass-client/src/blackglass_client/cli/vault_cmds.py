from __future__ import annotations
import sys
import click
from ..client import request
from ._output import _emit
from ._payloads import (
    patch_op_append,
    patch_op_prepend,
    patch_op_set_frontmatter,
    patch_op_replace,
)


def normalize_flat_path(path: str) -> str:
    """Normalize a path to flat-vault conventions.
    Strips leading / and ~/ and enforces .md extension.
    Warns and strips directory components if flat enforcement is enabled.
    """
    path = path.lstrip("/")
    path = path.removeprefix("~/")
    stem = path.removesuffix(".md")
    if "/" in stem or "\\" in stem:
        # Extract just the filename
        filename = path.rsplit("/", 1)[-1]
        print(f"WARN: Stripped directory prefix. Using '{filename}' instead.", file=sys.stderr)
        path = filename
    if not path.endswith(".md"):
        path = path + ".md"
    return path


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
    if path_glob is not None:
        path_glob = normalize_flat_path(path_glob)
        if path_glob != path_glob.removesuffix(".md"):
            # Was normalized, so strip .md for glob
            path_glob = path_glob.removesuffix(".md")
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
    path = normalize_flat_path(path)
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


# Filesystem aliases


@vault.command("cat")
@click.argument("path")
@click.pass_context
def cat(ctx: click.Context, path: str) -> None:
    """Read a note's content (alias for notes get)."""
    path = normalize_flat_path(path)
    _emit(request("GET", f"/vault/notes/{path}"), ctx.obj["pretty"])


@vault.command("ls")
@click.option("--tag", multiple=True, help="Filter to notes tagged with TAG. Repeatable.")
@click.option(
    "--fm",
    "fm_filters",
    multiple=True,
    callback=_parse_fm,
    help="Filter by frontmatter KEY=VALUE. Repeatable.",
)
@click.argument("path_glob", required=False)
@click.option("--limit", type=int, help="Cap result count.")
@click.pass_context
def ls(
    ctx: click.Context,
    tag: tuple[str, ...],
    fm_filters: dict[str, str],
    path_glob: str | None,
    limit: int | None,
) -> None:
    """List notes in the vault (alias for vault files)."""
    if path_glob is not None:
        path_glob = normalize_flat_path(path_glob)
        if path_glob != path_glob.removesuffix(".md"):
            path_glob = path_glob.removesuffix(".md")
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


@vault.command("head")
@click.argument("path")
@click.option("-n", "--lines", default=10, type=int, help="Number of lines to show (default: 10)")
@click.pass_context
def head(ctx: click.Context, path: str, lines: int) -> None:
    """Show first N lines of a note."""
    path = normalize_flat_path(path)
    resp = request("GET", f"/vault/notes/{path}")
    content = resp.get("content", "")
    lines_list = content.splitlines()[:lines]
    print("\n".join(lines_list))


@vault.command("tail")
@click.argument("path")
@click.option("-n", "--lines", default=10, type=int, help="Number of lines to show (default: 10)")
@click.pass_context
def tail(ctx: click.Context, path: str, lines: int) -> None:
    """Show last N lines of a note."""
    path = normalize_flat_path(path)
    resp = request("GET", f"/vault/notes/{path}")
    content = resp.get("content", "")
    lines_list = content.splitlines()[-lines:]
    print("\n".join(lines_list))


@vault.command("grep")
@click.argument("pattern")
@click.option("--limit", default=10, type=int, help="Max results (default: 10)")
@click.pass_context
def grep(ctx: click.Context, pattern: str, limit: int) -> None:
    """Search text across all notes (alias for search text)."""
    _emit(request("GET", "/search/text", params={"query": pattern, "limit": limit}), ctx.obj["pretty"])


@vault.command("find")
@click.argument("glob")
@click.pass_context
def find(ctx: click.Context, glob: str) -> None:
    """Find notes by filename glob (alias for vault files --path-glob)."""
    glob = normalize_flat_path(glob)
    if glob != glob.removesuffix(".md"):
        glob = glob.removesuffix(".md")
    _emit(request("GET", "/vault/files", params={"path_glob": glob}), ctx.obj["pretty"])


@vault.command("tree")
@click.option("--depth", default=1, type=int, help="Tree depth (ignored for flat vault)")
@click.pass_context
def tree(ctx: click.Context, depth: int) -> None:
    """Display vault structure as a tree."""
    resp = request("GET", "/vault/files")
    files = resp.get("files", [])
    print(".")
    for f in sorted(files):
        print(f"├── {f}")


@vault.command("mv")
@click.argument("src")
@click.argument("dst")
@click.pass_context
def mv(ctx: click.Context, src: str, dst: str) -> None:
    """Move or rename a note (alias for notes move)."""
    src = normalize_flat_path(src)
    dst = normalize_flat_path(dst)
    _emit(
        request(
            "POST",
            f"/vault/notes/{src}/move",
            json={"to": dst, "rewrite_links": True},
        ),
        ctx.obj["pretty"],
    )


@vault.command("rm")
@click.argument("path")
@click.pass_context
def rm(ctx: click.Context, path: str) -> None:
    """Delete a note (alias for notes delete)."""
    path = normalize_flat_path(path)
    request("DELETE", f"/vault/notes/{path}")


@vault.command("stat")
@click.argument("path")
@click.pass_context
def stat(ctx: click.Context, path: str) -> None:
    """Show note metadata (alias for notes meta)."""
    path = normalize_flat_path(path)
    _emit(request("GET", f"/vault/notes/{path}/meta"), ctx.obj["pretty"])


@vault.command("touch")
@click.argument("path")
@click.pass_context
def touch(ctx: click.Context, path: str) -> None:
    """Create an empty note (alias for notes create with empty content)."""
    path = normalize_flat_path(path)
    _emit(
        request("POST", "/vault/notes", params={"path": path}, json={"content": ""}),
        ctx.obj["pretty"],
    )


@vault.command("cp")
@click.argument("src")
@click.argument("dst")
@click.pass_context
def cp(ctx: click.Context, src: str, dst: str) -> None:
    """Copy a note's content to a new note."""
    src = normalize_flat_path(src)
    dst = normalize_flat_path(dst)
    resp = request("GET", f"/vault/notes/{src}")
    content = resp.get("content", "")
    _emit(
        request("POST", "/vault/notes", params={"path": dst}, json={"content": content}),
        ctx.obj["pretty"],
    )


@vault.command("edit")
@click.argument("path")
@click.option("--old", required=True)
@click.option("--new", required=True)
@click.option("--replace-all", is_flag=True)
@click.pass_context
def edit(ctx: click.Context, path: str, old: str, new: str, replace_all: bool) -> None:
    """Find-and-replace within a note (alias for notes replace)."""
    path = normalize_flat_path(path)
    _emit(
        request(
            "PATCH",
            f"/vault/notes/{path}",
            json=patch_op_replace(old, new, replace_all),
        ),
        ctx.obj["pretty"],
    )
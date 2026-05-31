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


@click.group()
def notes():
    """Note CRUD operations."""


@notes.command("get")
@click.argument("path")
@click.pass_context
def get_note(ctx: click.Context, path: str) -> None:
    """Get a note by vault-relative path."""
    _emit(request("GET", f"/vault/notes/{path}"), ctx.obj["pretty"])


@notes.command("meta")
@click.argument("path")
@click.pass_context
def note_meta(ctx: click.Context, path: str) -> None:
    """Get note metadata (size, mtime, frontmatter)."""
    _emit(request("GET", f"/vault/notes/{path}/meta"), ctx.obj["pretty"])


@notes.command("create")
@click.argument("path")
@click.option("--content", required=True, help="Note content (markdown).")
@click.pass_context
def create_note(ctx: click.Context, path: str, content: str) -> None:
    """Create a new note."""
    _emit(
        request("POST", "/vault/notes", params={"path": path}, json={"content": content}),
        ctx.obj["pretty"],
    )


@notes.command("update")
@click.argument("path")
@click.option("--content", required=True)
@click.pass_context
def update_note(ctx: click.Context, path: str, content: str) -> None:
    """Replace a note's content."""
    _emit(
        request("PUT", f"/vault/notes/{path}", json={"content": content}),
        ctx.obj["pretty"],
    )


@notes.command("append")
@click.argument("path")
@click.argument("content")
@click.pass_context
def append_note(ctx: click.Context, path: str, content: str) -> None:
    """Append content to a note."""
    _emit(
        request("PATCH", f"/vault/notes/{path}", json=patch_op_append(content)),
        ctx.obj["pretty"],
    )


@notes.command("prepend")
@click.argument("path")
@click.argument("content")
@click.pass_context
def prepend_note(ctx: click.Context, path: str, content: str) -> None:
    """Prepend content to a note (after frontmatter)."""
    _emit(
        request("PATCH", f"/vault/notes/{path}", json=patch_op_prepend(content)),
        ctx.obj["pretty"],
    )


@notes.command("set-frontmatter")
@click.argument("path")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set_frontmatter(ctx: click.Context, path: str, key: str, value: str) -> None:
    """Set a frontmatter field on a note."""
    _emit(
        request("PATCH", f"/vault/notes/{path}", json=patch_op_set_frontmatter(key, value)),
        ctx.obj["pretty"],
    )


@notes.command("replace")
@click.argument("path")
@click.option("--old", required=True, help="Anchor string to replace.")
@click.option("--new", required=True, help="Replacement string.")
@click.option("--replace-all", is_flag=True, help="Replace all occurrences (default: first only).")
@click.pass_context
def replace_note(ctx: click.Context, path: str, old: str, new: str, replace_all: bool) -> None:
    """Anchored find-and-replace in a note."""
    _emit(
        request(
            "PATCH",
            f"/vault/notes/{path}",
            json=patch_op_replace(old, new, replace_all),
        ),
        ctx.obj["pretty"],
    )


@notes.command("delete")
@click.argument("path")
def delete_note(path: str) -> None:
    """Delete a note."""
    request("DELETE", f"/vault/notes/{path}")


@notes.command("batch")
@click.argument("paths", nargs=-1)
@click.option("--stdin", "from_stdin", is_flag=True, help="Read newline-separated paths from stdin.")
@click.pass_context
def batch_read(ctx: click.Context, paths: tuple[str, ...], from_stdin: bool) -> None:
    """Batch-read multiple notes in one request (max 50)."""
    if from_stdin and paths:
        raise click.UsageError("--stdin and positional paths are mutually exclusive")
    if from_stdin:
        path_list = [line for line in sys.stdin.read().splitlines() if line]
    else:
        path_list = list(paths)
    _emit(
        request("POST", "/vault/notes/batch", json={"paths": path_list}),
        ctx.obj["pretty"],
    )


@notes.command("move")
@click.argument("src")
@click.argument("dst")
@click.option(
    "--rewrite-links/--no-rewrite-links",
    default=True,
    help="Rewrite wikilinks pointing to SRC (default: yes).",
)
@click.pass_context
def move_note(ctx: click.Context, src: str, dst: str, rewrite_links: bool) -> None:
    """Move/rename a note. Rewrites wikilinks by default."""
    _emit(
        request(
            "POST",
            f"/vault/notes/{src}/move",
            json={"to": dst, "rewrite_links": rewrite_links},
        ),
        ctx.obj["pretty"],
    )

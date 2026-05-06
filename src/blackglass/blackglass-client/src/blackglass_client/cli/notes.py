from __future__ import annotations
import json
import click
from ..client import request


@click.group()
def notes():
    """Note CRUD operations."""


def _out(data: dict | list, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"{k}: {v}")
        else:
            click.echo(data)


@notes.command("get")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def get_note(path: str, as_json: bool) -> None:
    """Get a note by vault-relative path."""
    data = request("GET", f"/vault/notes/{path}")
    _out(data, as_json)


@notes.command("create")
@click.argument("path")
@click.option("--content", required=True, help="Note content (markdown)")
@click.option("--json", "as_json", is_flag=True)
def create_note(path: str, content: str, as_json: bool) -> None:
    """Create a new note."""
    data = request("POST", "/vault/notes", params={"path": path}, json={"content": content})
    _out(data, as_json)


@notes.command("update")
@click.argument("path")
@click.option("--content", required=True)
@click.option("--json", "as_json", is_flag=True)
def update_note(path: str, content: str, as_json: bool) -> None:
    """Replace a note's content."""
    data = request("PUT", f"/vault/notes/{path}", json={"content": content})
    _out(data, as_json)


@notes.command("append")
@click.argument("path")
@click.argument("content")
@click.option("--json", "as_json", is_flag=True)
def append_note(path: str, content: str, as_json: bool) -> None:
    """Append content to a note."""
    data = request("PATCH", f"/vault/notes/{path}", json={"op": "append", "content": content})
    _out(data, as_json)


@notes.command("set-frontmatter")
@click.argument("path")
@click.argument("key")
@click.argument("value")
@click.option("--json", "as_json", is_flag=True)
def set_frontmatter(path: str, key: str, value: str, as_json: bool) -> None:
    """Set a frontmatter field on a note."""
    data = request(
        "PATCH",
        f"/vault/notes/{path}",
        json={"op": "set_frontmatter", "key": key, "value": value},
    )
    _out(data, as_json)


@notes.command("delete")
@click.argument("path")
def delete_note(path: str) -> None:
    """Delete a note."""
    request("DELETE", f"/vault/notes/{path}")
    click.echo(f"Deleted: {path}")

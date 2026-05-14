from __future__ import annotations
import json
import click
from ..client import request


def _out(data: dict | list, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, list):
            for item in data:
                click.echo(item if isinstance(item, str) else json.dumps(item))
        else:
            click.echo(json.dumps(data, indent=2))


@click.group()
def vault():
    """Vault-level operations."""


@vault.command("files")
@click.option("--json", "as_json", is_flag=True)
def files(as_json: bool) -> None:
    """List all notes in the vault."""
    _out(request("GET", "/vault/files"), as_json)


@vault.command("tags")
@click.option("--json", "as_json", is_flag=True)
def tags(as_json: bool) -> None:
    """List all tags with counts."""
    _out(request("GET", "/vault/tags"), as_json)


@vault.command("periodic")
@click.option("--json", "as_json", is_flag=True)
def periodic(as_json: bool) -> None:
    """List periodic (daily) notes."""
    _out(request("GET", "/vault/periodic"), as_json)


@vault.command("backlinks")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
def backlinks(path: str, as_json: bool) -> None:
    """List notes that link to PATH."""
    _out(request("GET", f"/vault/backlinks/{path}"), as_json)


@vault.command("sync")
def sync() -> None:
    """Git pull and re-index changed notes."""
    result = request("POST", "/vault/sync")
    click.echo(f"git: {result.get('git', '')}")
    click.echo(f"checked: {result['files_checked']}  indexed: {result['files_indexed']}")

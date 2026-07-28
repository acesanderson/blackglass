from __future__ import annotations
import click
from .notes import notes
from .vault_cmds import vault
from .search_cmds import search
from .obs_cmds import obs
from .publish import publish


@click.group()
@click.option("--pretty", is_flag=True, help="Pretty-print JSON output (indent=2).")
@click.pass_context
def cli(ctx: click.Context, pretty: bool) -> None:
    """Blackglass: Obsidian vault over HTTP."""
    ctx.ensure_object(dict)
    ctx.obj["pretty"] = pretty


cli.add_command(notes)
cli.add_command(vault)
cli.add_command(search)
cli.add_command(obs)
cli.add_command(publish)

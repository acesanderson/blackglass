from __future__ import annotations
import click
from .notes import notes
from .vault_cmds import vault
from .search_cmds import search


@click.group()
def cli():
    """Blackglass — Obsidian vault over HTTP."""


cli.add_command(notes)
cli.add_command(vault)
cli.add_command(search)

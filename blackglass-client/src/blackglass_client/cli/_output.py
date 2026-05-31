from __future__ import annotations
import json
import click


def _emit(data: dict | list | None, pretty: bool) -> None:
    if data is None:
        return
    if pretty:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(json.dumps(data, separators=(",", ":")))

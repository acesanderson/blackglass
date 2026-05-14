from __future__ import annotations
import json
import click
from ..client import request


def _out(data: list, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for item in data:
            click.echo(f"  {item['path']}")
            if "excerpt" in item:
                click.echo(f"    {item['excerpt'][:120]}")
            if "score" in item:
                click.echo(f"    score: {item['score']:.3f}")


@click.group()
def search():
    """Search the vault."""


@search.command("text")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
def text_search(query: str, as_json: bool) -> None:
    """Full-text search across all notes."""
    results = request("GET", "/vault/search", params={"q": query})
    _out(results, as_json)


@search.command("semantic")
@click.argument("query")
@click.option("--limit", default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def semantic_search(query: str, limit: int, as_json: bool) -> None:
    """Semantic (embedding) search across indexed notes."""
    results = request("GET", "/vault/semantic-search", params={"q": query, "limit": limit})
    _out(results, as_json)

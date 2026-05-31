from __future__ import annotations
import click
from ..client import request
from ._output import _emit


@click.group()
@click.pass_context
def search(ctx: click.Context) -> None:
    """Search the vault."""
    ctx.ensure_object(dict)
    ctx.obj.setdefault("pretty", False)


@search.command("text")
@click.argument("query")
@click.option("--snippet-chars", type=int, help="Snippet length per hit (0..1000, default 300).")
@click.pass_context
def text_search(ctx: click.Context, query: str, snippet_chars: int | None) -> None:
    """Full-text search across all notes."""
    params: dict[str, str] = {"q": query}
    if snippet_chars is not None:
        params["snippet_chars"] = str(snippet_chars)
    _emit(request("GET", "/vault/search", params=params), ctx.obj["pretty"])


@search.command("semantic")
@click.argument("query")
@click.option("--limit", type=int, help="Result cap (1..100, default 10).")
@click.option("--snippet-chars", type=int, help="Snippet length per hit (0..1000, default 300).")
@click.pass_context
def semantic_search(
    ctx: click.Context, query: str, limit: int | None, snippet_chars: int | None
) -> None:
    """Semantic (embedding) search across indexed notes."""
    params: dict[str, str] = {"q": query}
    if limit is not None:
        params["limit"] = str(limit)
    if snippet_chars is not None:
        params["snippet_chars"] = str(snippet_chars)
    _emit(request("GET", "/vault/semantic-search", params=params), ctx.obj["pretty"])


@search.command("hybrid")
@click.argument("query")
@click.option("--limit", type=int, help="Result cap (1..100, default 10).")
@click.option("--snippet-chars", type=int, help="Snippet length per hit (0..1000, default 300).")
@click.option("--k", type=int, help="RRF k constant (1..1000, default 60).")
@click.pass_context
def hybrid_search(
    ctx: click.Context,
    query: str,
    limit: int | None,
    snippet_chars: int | None,
    k: int | None,
) -> None:
    """Hybrid (text + semantic) search with reciprocal rank fusion."""
    params: dict[str, str] = {"q": query}
    if limit is not None:
        params["limit"] = str(limit)
    if snippet_chars is not None:
        params["snippet_chars"] = str(snippet_chars)
    if k is not None:
        params["k"] = str(k)
    _emit(request("GET", "/vault/hybrid-search", params=params), ctx.obj["pretty"])

# cli/self_tune/cli.py
"""Self-tune CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .store import SelfTuneStore
from .export import export_sft, export_dpo, export_jsonl

console = Console()
DEFAULT_ROOT = Path.home() / ".self-tune"


def _store() -> SelfTuneStore:
    store = SelfTuneStore(DEFAULT_ROOT)
    if not (DEFAULT_ROOT / "data").exists():
        console.print("[yellow]No data directory found. Run install.sh first.[/yellow]")
        raise SystemExit(1)
    return store


@click.group()
def main():
    """Self-tune: Extract learning experiences from AI coding interactions."""
    pass


@main.command()
def stats():
    """Show local data statistics."""
    store = _store()
    s = store.stats()
    table = Table(title="Self-tune Local Data")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right", style="green")
    for key, val in s.items():
        label = key.replace("total_", "").replace("_", " ").title()
        table.add_row(label, str(val))
    console.print(table)


@main.command(name="list")
@click.option("--type", "item_type", type=click.Choice(["insights", "samples", "traces", "corrections"]), default="insights")
@click.option("--limit", default=20, help="Max items to show")
def list_items(item_type: str, limit: int):
    """List stored items."""
    store = _store()
    loader = getattr(store, f"list_{item_type}")
    items = loader()[:limit]
    if not items:
        console.print(f"[dim]No {item_type} found.[/dim]")
        return
    table = Table(title=f"{item_type.title()} ({len(items)})")
    table.add_column("ID", style="cyan")
    table.add_column("Created", style="dim")
    table.add_column("Detail")
    for item in items:
        detail = ""
        if hasattr(item, "insight_type"):
            detail = item.insight_type.value
        elif hasattr(item, "sft_type"):
            detail = item.sft_type.value
        elif hasattr(item, "status"):
            detail = item.status.value if hasattr(item.status, "value") else str(item.status)
        table.add_row(item.id, str(item.created_at)[:10], detail)
    console.print(table)


@main.command()
@click.argument("item_id")
def show(item_id: str):
    """Show details of a specific item."""
    store = _store()
    prefix = item_id.split("-")[0]
    loaders = {
        "trace": store.load_trace,
        "ins": store.load_insight,
        "sft": store.load_sample,
        "cor": store.load_correction,
    }
    loader = loaders.get(prefix)
    if not loader:
        console.print(f"[red]Unknown ID prefix: {prefix}[/red]")
        raise SystemExit(1)
    item = loader(item_id)
    console.print_json(item.model_dump_json(indent=2))


@main.command()
@click.option("--format", "fmt", type=click.Choice(["sft", "dpo", "jsonl"]), default="sft")
@click.option("--output", "-o", type=click.Path(), default="self-tune-export.jsonl")
@click.option("--min-score", type=float, default=None, help="Minimum quality score filter")
def export(fmt: str, output: str, min_score: float | None):
    """Export SFT training data."""
    store = _store()
    output_path = Path(output)
    exporters = {"sft": export_sft, "dpo": export_dpo, "jsonl": export_jsonl}
    count = exporters[fmt](store, output_path, min_score=min_score)
    console.print(f"[green]Exported {count} samples to {output_path} ({fmt} format)[/green]")

# cli/self_tune/cli.py
"""Self-tune CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .store import SelfTuneStore
from .export import export_sft, export_dpo, export_jsonl, export_anthropic, export_chatml, export_ml2

import json as _json

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

    # Review status breakdown
    samples = store.list_samples()
    if samples:
        review_table = Table(title="Review Status")
        review_table.add_column("Status", style="cyan")
        review_table.add_column("Count", justify="right", style="green")
        from collections import Counter
        status_counts = Counter(s.review_status for s in samples)
        for status in ["pending", "approved", "rejected"]:
            review_table.add_row(status, str(status_counts.get(status, 0)))
        console.print(review_table)


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
@click.option("--format", "fmt", type=click.Choice(["ml2", "sft", "anthropic", "chatml", "dpo", "jsonl"]), default="ml2")
@click.option("--output", "-o", type=click.Path(), default="self-tune-export.jsonl")
@click.option("--min-score", type=float, default=None, help="Minimum quality score filter")
@click.option("--include-pending", is_flag=True, default=False, help="Include pending (unreviewed) samples")
def export(fmt: str, output: str, min_score: float | None, include_pending: bool):
    """Export SFT training data."""
    store = _store()
    output_path = Path(output)
    exporters = {"ml2": export_ml2, "sft": export_sft, "anthropic": export_anthropic, "chatml": export_chatml, "dpo": export_dpo, "jsonl": export_jsonl}
    count = exporters[fmt](store, output_path, min_score=min_score, include_pending=include_pending)
    if count == 0 and not include_pending:
        total = len(store.list_samples())
        if total > 0:
            console.print(f"[yellow]Note: {total} sample(s) exist but none are approved. "
                          f"Use --include-pending or run `self-tune review` first.[/yellow]")
    console.print(f"[green]Exported {count} samples to {output_path} ({fmt} format)[/green]")


@main.command()
@click.option("--status", type=click.Choice(["pending", "approved", "rejected"]), default="pending", help="Filter by review status")
def review(status: str):
    """Review SFT samples interactively."""
    store = _store()
    samples = [s for s in store.list_samples() if s.review_status == status]
    if not samples:
        console.print(f"[dim]No {status} samples to review.[/dim]")
        return

    console.print(f"[bold]{len(samples)} {status} sample(s) to review[/bold]\n")

    approved = 0
    rejected = 0
    skipped = 0

    for i, sample in enumerate(samples, 1):
        console.rule(f"[bold cyan]Sample {i}/{len(samples)}: {sample.id}[/bold cyan]")
        console.print(f"  Type: [yellow]{sample.sft_type.value}[/yellow]")
        console.print(f"  Insight: {sample.insight_id}")
        console.print(f"  Quality: {sample.quality.local_score}")
        console.print(f"  Decision point: {sample.query.decision_point}")
        console.print()

        # Show CoT (truncated if long)
        cot_preview = sample.cot[:500] + "..." if len(sample.cot) > 500 else sample.cot
        console.print("[bold]CoT:[/bold]")
        console.print(f"  {cot_preview}")
        console.print()

        # Show response + action
        console.print(f"[bold]Response:[/bold] {sample.response}")
        if sample.action:
            input_preview = _json.dumps(sample.action.input, ensure_ascii=False)[:100] if isinstance(sample.action.input, dict) else sample.action.input[:100]
            console.print(f"[bold]Action:[/bold] {sample.action.tool}({input_preview})")
        console.print()

        # Quality flags
        flags = []
        if sample.quality.evidence_anchored is False:
            flags.append("[red]NOT evidence-anchored[/red]")
        if sample.quality.no_post_hoc_rationalization is False:
            flags.append("[red]has post-hoc rationalization[/red]")
        if flags:
            console.print("  ".join(flags))
            console.print()

        choice = click.prompt(
            "  [a]pprove / [r]eject / [s]kip / [f]ull detail / [q]uit",
            type=click.Choice(["a", "r", "s", "f", "q"], case_sensitive=False),
            default="s",
        )

        if choice == "f":
            console.print_json(sample.model_dump_json(indent=2))
            choice = click.prompt(
                "  [a]pprove / [r]eject / [s]kip / [q]uit",
                type=click.Choice(["a", "r", "s", "q"], case_sensitive=False),
                default="s",
            )

        if choice == "a":
            store.update_sample(sample.id, review_status="approved")
            approved += 1
            console.print("  [green]Approved[/green]")
        elif choice == "r":
            store.update_sample(sample.id, review_status="rejected")
            rejected += 1
            console.print("  [red]Rejected[/red]")
        elif choice == "q":
            console.print("[dim]Review session ended.[/dim]")
            break
        else:
            skipped += 1

    console.print(f"\n[bold]Review summary:[/bold] {approved} approved, {rejected} rejected, {skipped} skipped")

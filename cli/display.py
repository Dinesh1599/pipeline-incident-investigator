"""
display.py — Rich terminal output for the investigation CLI.

Streams investigation progress as each node completes, then
displays the final structured report with colored sections.

"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich import box

console = Console()


def print_banner():
    """Print the application banner."""
    console.print(
        Panel(
            "[bold cyan]AI Data Pipeline Incident Investigator[/bold cyan]\n"
            "[dim]Powered by LangGraph + GPT-4o[/dim]",
            box=box.DOUBLE,
            border_style="cyan",
        )
    )


def print_step(node: str, message: str, style: str = ""):
    """Print a streaming investigation step."""
    node_colors = {
        "INTAKE": "bold white",
        "CONTEXT": "blue",
        "SIGNALS": "yellow",
        "CLASSIFY": "magenta",
        "ROUTER": "dim",
        "EVIDENCE": "green",
        "CODE": "cyan",
        "LINEAGE": "blue",
        "RETRIEVAL": "yellow",
        "REASONING": "bold magenta",
        "FIX": "bold green",
        "REPORT": "bold white",
    }
    color = node_colors.get(node, "white")
    console.print(f"  [{color}][{node}][/{color}] {message}")


def print_report(report: dict):
    """Print the full investigation report with rich formatting."""
    console.print()
    console.print(
        Panel(
            "[bold]INVESTIGATION REPORT[/bold]",
            box=box.HEAVY,
            border_style="cyan",
            expand=False,
        )
    )

    # Header info
    header = Table(show_header=False, box=None, padding=(0, 2))
    header.add_column(style="bold")
    header.add_column()
    header.add_row("Incident ID", report.get("incident_id", ""))
    header.add_row("Severity", _severity_badge(report.get("severity", "error")))
    header.add_row("Failure Class", report.get("failure_class", "unknown"))
    header.add_row("Confidence", _confidence_bar(report.get("confidence", 0.0)))
    console.print(header)
    console.print()

    # What Failed
    console.print(Panel(
        report.get("what_failed") or "Unknown",
        title="[bold red]What Failed[/bold red]",
        border_style="red",
    ))

    # Where Failed
    where = report.get("where_failed", {})
    where_table = Table(show_header=False, box=None, padding=(0, 2))
    where_table.add_column(style="bold dim")
    where_table.add_column()
    where_table.add_row("DAG", where.get("dag_id", ""))
    where_table.add_row("Task", where.get("task_id", ""))
    where_table.add_row("Model", where.get("model", ""))
    where_table.add_row("Table", where.get("table", ""))
    where_table.add_row("Column", where.get("column", ""))
    console.print(Panel(
        where_table,
        title="[bold yellow]Where It Failed[/bold yellow]",
        border_style="yellow",
    ))

    # How It Failed
    console.print(Panel(
        report.get("how_it_failed") or "Not determined",
        title="[bold]How It Failed[/bold]",
        border_style="white",
    ))

    # Root Cause
    console.print(Panel(
        report.get("root_cause") or "Unable to determine",
        title="[bold magenta]Root Cause[/bold magenta]",
        border_style="magenta",
    ))

    # Evidence Chain
    evidence = report.get("evidence_chain", [])
    if evidence:
        evidence_text = "\n".join(f"  {i}. {e}" for i, e in enumerate(evidence, 1))
        console.print(Panel(
            evidence_text,
            title="[bold]Evidence Chain[/bold]",
            border_style="blue",
        ))

    # Alternatives Considered
    alternatives = report.get("alternative_causes_considered", [])
    if alternatives:
        alt_text = ""
        for alt in alternatives:
            alt_text += f"  • {alt.get('cause', '')}\n"
            alt_text += f"    [dim]Ruled out by: {alt.get('ruled_out_by', '')}[/dim]\n"
        console.print(Panel(
            alt_text.strip(),
            title="[bold]Alternatives Considered[/bold]",
            border_style="dim",
        ))

    # Fix Recommendations
    fix = report.get("fix", {})
    if fix:
        fix_table = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
        fix_table.add_column("Category", style="bold")
        fix_table.add_column("Recommendation")
        if fix.get("immediate"):
            fix_table.add_row("[red]Immediate[/red]", fix["immediate"])
        if fix.get("preventive"):
            fix_table.add_row("[yellow]Preventive[/yellow]", fix["preventive"])
        if fix.get("monitoring"):
            fix_table.add_row("[green]Monitoring[/green]", fix["monitoring"])
        console.print(Panel(
            fix_table,
            title="[bold green]Fix Recommendations[/bold green]",
            border_style="green",
        ))

    # Prevention
    prevention = report.get("prevention", [])
    if prevention:
        prev_text = "\n".join(f"  • {p}" for p in prevention)
        console.print(Panel(
            prev_text,
            title="[bold]Additional Prevention[/bold]",
            border_style="dim",
        ))


def print_error(message: str):
    """Print an error message."""
    console.print(f"[bold red]ERROR:[/bold red] {message}")


def print_success(message: str):
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def _severity_badge(severity: str) -> str:
    """Format severity as a colored badge."""
    colors = {
        "error": "[bold red]ERROR[/bold red]",
        "warning": "[bold yellow]WARNING[/bold yellow]",
        "info": "[bold blue]INFO[/bold blue]",
    }
    return colors.get(severity, severity)


def _confidence_bar(confidence: float) -> str:
    """Format confidence as a colored bar."""
    pct = int(confidence * 100)
    filled = int(confidence * 20)
    empty = 20 - filled

    if confidence >= 0.8:
        color = "green"
    elif confidence >= 0.5:
        color = "yellow"
    else:
        color = "red"

    bar = f"[{color}]{'█' * filled}{'░' * empty}[/{color}] {pct}%"
    return bar

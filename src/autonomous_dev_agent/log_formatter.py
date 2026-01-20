"""Log formatting utilities for CLI display.

Provides pretty formatting for session logs including:
- Session list table formatting
- Single session detail view
- Real-time streaming output
- JSON export formatting
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax

from .models import LogEntryType, SessionIndexEntry, SessionIndex
from .session_logger import read_session_log, stream_session_log, get_session_summary


# Windows-compatible symbols
if sys.platform == "win32":
    SYM_OK = "[OK]"
    SYM_FAIL = "[X]"
    SYM_ARROW = "->"
else:
    SYM_OK = "\u2713"
    SYM_FAIL = "\u2717"
    SYM_ARROW = "\u2192"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "5m 30s", "2h 15m")
    """
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def format_cost(cost_usd: float) -> str:
    """Format cost in dollars.

    Args:
        cost_usd: Cost in USD

    Returns:
        Formatted cost string
    """
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    elif cost_usd < 1.0:
        return f"${cost_usd:.3f}"
    else:
        return f"${cost_usd:.2f}"


def format_tokens(tokens: int) -> str:
    """Format token count with k/M suffixes.

    Args:
        tokens: Token count

    Returns:
        Formatted string (e.g., "45.2k", "1.2M")
    """
    if tokens < 1000:
        return str(tokens)
    elif tokens < 1000000:
        return f"{tokens / 1000:.1f}k"
    else:
        return f"{tokens / 1000000:.1f}M"


def format_session_list(
    sessions: list[SessionIndexEntry],
    console: Optional[Console] = None
) -> Table:
    """Format a list of sessions as a Rich table.

    Args:
        sessions: List of session entries
        console: Optional Rich console

    Returns:
        Rich Table
    """
    table = Table(title="Sessions", show_header=True, header_style="bold cyan")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Feature", style="white")
    table.add_column("Outcome", style="white")
    table.add_column("Turns", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Duration", justify="right")

    outcome_colors = {
        "success": "green",
        "failure": "red",
        "handoff": "yellow",
        "timeout": "red",
    }

    for session in sessions:
        # Calculate duration
        duration = ""
        if session.started_at and session.ended_at:
            secs = (session.ended_at - session.started_at).total_seconds()
            duration = format_duration(secs)

        # Format outcome with color
        outcome = session.outcome or "unknown"
        outcome_color = outcome_colors.get(outcome, "white")
        outcome_str = f"[{outcome_color}]{outcome}[/{outcome_color}]"

        # Truncate session ID for display
        session_id = session.session_id
        if len(session_id) > 30:
            session_id = session_id[:27] + "..."

        # Truncate feature ID
        feature = session.feature_id or "-"
        if len(feature) > 20:
            feature = feature[:17] + "..."

        table.add_row(
            session_id,
            feature,
            outcome_str,
            str(session.turns),
            format_tokens(session.tokens_total),
            duration
        )

    return table


def format_session_detail(
    log_path: Path,
    console: Optional[Console] = None
) -> list:
    """Format detailed view of a single session.

    Args:
        log_path: Path to the session JSONL file
        console: Optional Rich console

    Returns:
        List of Rich renderables
    """
    entries = read_session_log(log_path)
    if not entries:
        return [Text("No log entries found", style="yellow")]

    renderables = []
    console = console or Console()

    for entry in entries:
        entry_type = entry.get("type")
        timestamp = entry.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                pass

        if entry_type == LogEntryType.SESSION_START.value:
            panel = Panel(
                f"[bold]Session:[/bold] {entry.get('session_id')}\n"
                f"[bold]Agent:[/bold] {entry.get('agent_type')}\n"
                f"[bold]Feature:[/bold] {entry.get('feature_id') or 'N/A'}\n"
                f"[bold]Model:[/bold] {entry.get('model')}",
                title=f"[green]Session Start[/green] [{timestamp}]",
                border_style="green"
            )
            renderables.append(panel)

        elif entry_type == LogEntryType.PROMPT.value:
            prompt_name = entry.get("prompt_name", "")
            prompt_length = entry.get("prompt_length", 0)
            renderables.append(
                Text(f"[{timestamp}] Prompt: {prompt_name} ({prompt_length} chars)",
                     style="dim")
            )

        elif entry_type == LogEntryType.ASSISTANT.value:
            turn = entry.get("turn", 0)
            content = entry.get("content", "")
            tool_calls = entry.get("tool_calls", [])

            if content:
                # Show truncated content
                display_content = content[:500]
                if len(content) > 500:
                    display_content += "..."
                renderables.append(
                    Panel(
                        display_content,
                        title=f"[cyan]Turn {turn}[/cyan] [{timestamp}]",
                        border_style="cyan"
                    )
                )

            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get("tool", "unknown")
                    renderables.append(
                        Text(f"  {SYM_ARROW} Tool: {tool_name}", style="blue")
                    )

        elif entry_type == LogEntryType.TOOL_RESULT.value:
            tool = entry.get("tool", "")
            duration = entry.get("duration_ms", 0)
            file_changed = entry.get("file_changed", "")

            result_text = f"  {SYM_OK} {tool}"
            if duration:
                result_text += f" ({duration}ms)"
            if file_changed:
                result_text += f" - changed: {file_changed}"

            renderables.append(Text(result_text, style="dim green"))

        elif entry_type == LogEntryType.CONTEXT_UPDATE.value:
            total_tokens = entry.get("total_tokens", 0)
            context_pct = entry.get("context_percent", 0)

            renderables.append(
                Text(
                    f"  Context: {format_tokens(total_tokens)} tokens "
                    f"({context_pct:.1f}%)",
                    style="dim"
                )
            )

        elif entry_type == LogEntryType.ERROR.value:
            category = entry.get("category", "unknown")
            message = entry.get("message", "")
            renderables.append(
                Panel(
                    f"[bold]{category}[/bold]\n{message}",
                    title=f"[red]Error[/red] [{timestamp}]",
                    border_style="red"
                )
            )

        elif entry_type == LogEntryType.SESSION_END.value:
            outcome = entry.get("outcome", "unknown")
            duration = entry.get("duration_seconds", 0)
            turns = entry.get("turns", 0)
            files = entry.get("files_changed", [])

            outcome_color = "green" if outcome == "success" else "yellow" if outcome == "handoff" else "red"

            content = f"[bold]Outcome:[/bold] [{outcome_color}]{outcome}[/{outcome_color}]\n"
            content += f"[bold]Duration:[/bold] {format_duration(duration)}\n"
            content += f"[bold]Turns:[/bold] {turns}\n"

            if files:
                content += f"[bold]Files changed:[/bold]\n"
                for f in files[:10]:
                    content += f"  - {f}\n"
                if len(files) > 10:
                    content += f"  ... and {len(files) - 10} more"

            panel = Panel(
                content.strip(),
                title=f"[{outcome_color}]Session End[/{outcome_color}] [{timestamp}]",
                border_style=outcome_color
            )
            renderables.append(panel)

    return renderables


def stream_session_pretty(
    log_path: Path,
    console: Optional[Console] = None,
    follow: bool = False
) -> Generator[str, None, None]:
    """Stream session log with pretty formatting.

    Args:
        log_path: Path to the session JSONL file
        console: Optional Rich console
        follow: Whether to follow (tail -f style)

    Yields:
        Formatted log lines
    """
    for entry in stream_session_log(log_path, follow=follow):
        entry_type = entry.get("type")
        timestamp = entry.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                pass

        if entry_type == LogEntryType.SESSION_START.value:
            yield f"\n[{timestamp}] Session started: {entry.get('session_id')}"
            yield f"  Agent: {entry.get('agent_type')}, Model: {entry.get('model')}"
            if entry.get('feature_id'):
                yield f"  Feature: {entry.get('feature_id')}"

        elif entry_type == LogEntryType.PROMPT.value:
            yield f"[{timestamp}] Prompt sent ({entry.get('prompt_length')} chars)"

        elif entry_type == LogEntryType.ASSISTANT.value:
            turn = entry.get("turn", 0)
            content = entry.get("content", "")
            tool_calls = entry.get("tool_calls", [])

            if content:
                preview = content[:100].replace("\n", " ")
                if len(content) > 100:
                    preview += "..."
                yield f"[{timestamp}] Turn {turn}: {preview}"

            for tc in tool_calls:
                yield f"  {SYM_ARROW} Tool: {tc.get('tool', 'unknown')}"

        elif entry_type == LogEntryType.TOOL_RESULT.value:
            tool = entry.get("tool", "")
            duration = entry.get("duration_ms")
            duration_str = f" ({duration}ms)" if duration else ""
            yield f"  {SYM_OK} {tool}{duration_str}"

        elif entry_type == LogEntryType.CONTEXT_UPDATE.value:
            pct = entry.get("context_percent", 0)
            yield f"  Context: {pct:.1f}%"

        elif entry_type == LogEntryType.ERROR.value:
            category = entry.get("category", "unknown")
            message = entry.get("message", "")[:100]
            yield f"[{timestamp}] ERROR ({category}): {message}"

        elif entry_type == LogEntryType.SESSION_END.value:
            outcome = entry.get("outcome", "unknown")
            duration = entry.get("duration_seconds", 0)
            yield f"\n[{timestamp}] Session ended: {outcome}"
            yield f"  Duration: {format_duration(duration)}"


def format_workspace_info(stats: dict, console: Optional[Console] = None) -> list:
    """Format workspace statistics for display.

    Args:
        stats: Stats dict from WorkspaceManager.get_workspace_stats()
        console: Optional Rich console

    Returns:
        List of Rich renderables
    """
    renderables = []

    # Project info panel
    project_content = f"[bold]Name:[/bold] {stats.get('project_name', 'Unknown')}\n"
    if stats.get('project_description'):
        desc = stats['project_description']
        if len(desc) > 200:
            desc = desc[:197] + "..."
        project_content += f"[bold]Description:[/bold] {desc}\n"
    if stats.get('created_at'):
        project_content += f"[bold]Created:[/bold] {stats['created_at'][:10]}"

    renderables.append(Panel(
        project_content.strip(),
        title="Project",
        border_style="cyan"
    ))

    # Initialization info panel (if spec was used)
    if stats.get('init_session'):
        init = stats['init_session']
        init_content = f"[bold]Spec File:[/bold] {init.get('spec_file', 'N/A')}\n"
        init_content += f"[bold]Features Generated:[/bold] {init.get('feature_count', 0)}\n"
        init_content += f"[bold]Model:[/bold] {init.get('model', 'N/A')}\n"
        if init.get('generated_at'):
            init_content += f"[bold]Generated:[/bold] {init['generated_at'][:10]}"

        renderables.append(Panel(
            init_content.strip(),
            title="Initialization",
            border_style="blue"
        ))

    # Stats table
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="green")

    table.add_row("Total Sessions", str(stats.get("total_sessions", 0)))
    table.add_row("Total Tokens", format_tokens(stats.get("total_tokens", 0)))

    duration = stats.get("total_duration_seconds", 0)
    if duration > 0:
        table.add_row("Total Time", format_duration(duration))

    log_size_mb = stats.get("log_size_mb", 0)
    threshold_mb = stats.get("rotation_threshold_mb", 100)
    table.add_row("Log Size", f"{log_size_mb:.1f}MB / {threshold_mb:.0f}MB")

    renderables.append(table)

    # Outcomes breakdown if available
    outcomes = stats.get("outcomes", {})
    if outcomes:
        outcome_text = Text()
        outcome_colors = {
            "success": "green",
            "failure": "red",
            "handoff": "yellow",
            "timeout": "red",
        }
        for outcome, count in outcomes.items():
            color = outcome_colors.get(outcome, "white")
            outcome_text.append(f"{outcome}: ", style="bold")
            outcome_text.append(f"{count}  ", style=color)

        renderables.append(Text())
        renderables.append(Text("Session Outcomes:", style="bold"))
        renderables.append(outcome_text)

    return renderables


def export_sessions_to_jsonl(
    sessions_dir: Path,
    output_path: Path,
    session_ids: Optional[list[str]] = None
) -> int:
    """Export session logs to a single JSONL file.

    Args:
        sessions_dir: Directory containing session JSONL files
        output_path: Path for the output file
        session_ids: Optional list of session IDs to export (all if None)

    Returns:
        Number of entries exported
    """
    import json

    count = 0
    with open(output_path, "w", encoding="utf-8") as out:
        for log_file in sorted(sessions_dir.glob("*.jsonl")):
            # Check if we should include this session
            session_id = log_file.stem
            if session_ids and session_id not in session_ids:
                continue

            # Read and write all entries
            entries = read_session_log(log_file)
            for entry in entries:
                # Add session_id to each entry for context
                if "session_id" not in entry:
                    entry["session_id"] = session_id
                out.write(json.dumps(entry, default=str) + "\n")
                count += 1

    return count

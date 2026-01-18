"""CLI interface for the Autonomous Development Agent."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .models import Backlog, Feature, FeatureStatus, FeatureCategory, HarnessConfig, SessionMode
from .harness import AutonomousHarness
from .git_manager import GitManager

console = Console()


@click.group()
@click.version_option()
def main():
    """Autonomous Development Agent - Long-running coding agent harness."""
    pass


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--mode', type=click.Choice(['cli', 'sdk']), default='cli',
              help='Session mode: cli (uses subscription, reliable) or sdk (uses API credits, Windows issues)')
@click.option('--model', default='claude-opus-4-5-20251101', help='Claude model to use')
@click.option('--threshold', default=70.0, help='Context threshold percentage for handoff')
@click.option('--max-sessions', type=int, help='Maximum sessions before stopping')
@click.option('--max-turns', default=100, help='Maximum turns per session (CLI mode only)')
@click.option('--backlog', default='feature-list.json', help='Backlog file name')
def run(
    project_path: str,
    mode: str,
    model: str,
    threshold: float,
    max_sessions: Optional[int],
    max_turns: int,
    backlog: str
):
    """Run the autonomous agent on a project.

    PROJECT_PATH is the path to the project directory containing feature-list.json.

    Two modes are available:

    \b
    --mode cli (default, recommended):
      - Uses the Claude CLI directly
      - Billed to your Claude subscription (Pro/Max)
      - More reliable on Windows
      - Shows full output when complete

    \b
    --mode sdk:
      - Uses the Claude Agent SDK
      - Billed to Anthropic API credits (separate from subscription)
      - Streaming output with verbose logging
      - Known reliability issues on Windows (exit code 1 bug)
    """
    session_mode = SessionMode.CLI if mode == 'cli' else SessionMode.SDK

    config = HarnessConfig(
        session_mode=session_mode,
        model=model,
        context_threshold_percent=threshold,
        max_sessions=max_sessions,
        cli_max_turns=max_turns,
        backlog_file=backlog
    )

    console.print(f"[bold]Mode:[/bold] {mode.upper()} ({'subscription' if mode == 'cli' else 'API credits'})")
    console.print(f"[bold]Model:[/bold] {model}")

    harness = AutonomousHarness(project_path, config)

    try:
        asyncio.run(harness.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@main.command()
@click.argument('project_path', type=click.Path())
@click.option('--name', prompt='Project name', help='Name of the project')
def init(project_path: str, name: str):
    """Initialize a new project for autonomous development.

    Creates the feature-list.json and directory structure.
    """
    path = Path(project_path)
    path.mkdir(parents=True, exist_ok=True)

    backlog = Backlog(
        project_name=name,
        project_path=str(path.resolve()),
        features=[]
    )

    backlog_file = path / "feature-list.json"
    if backlog_file.exists():
        console.print(f"[yellow]Backlog already exists at {backlog_file}[/yellow]")
        return

    backlog_file.write_text(backlog.model_dump_json(indent=2))
    console.print(f"[green]OK[/green] Created {backlog_file}")
    console.print(f"\nNext steps:")
    console.print(f"  1. Add features: ada add-feature {project_path} --name 'Feature name'")
    console.print(f"  2. Run agent: ada run {project_path}")


@main.command('add-feature')
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--name', prompt='Feature name', help='Name of the feature')
@click.option('--description', prompt='Description', help='Feature description')
@click.option('--category', type=click.Choice(['functional', 'bugfix', 'refactor', 'testing', 'documentation', 'infrastructure']),
              default='functional', help='Feature category')
@click.option('--priority', default=0, help='Priority (higher = more urgent)')
@click.option('--criteria', multiple=True, help='Acceptance criteria (can specify multiple)')
@click.option('--depends-on', multiple=True, help='Feature IDs this depends on')
def add_feature(
    project_path: str,
    name: str,
    description: str,
    category: str,
    priority: int,
    criteria: tuple,
    depends_on: tuple
):
    """Add a feature to the backlog."""
    path = Path(project_path)
    backlog_file = path / "feature-list.json"

    if not backlog_file.exists():
        console.print(f"[red]No backlog found. Run 'ada init {project_path}' first.[/red]")
        return

    backlog = Backlog.model_validate_json(backlog_file.read_text())

    # Generate ID from name
    feature_id = name.lower().replace(' ', '-').replace('_', '-')
    feature_id = ''.join(c for c in feature_id if c.isalnum() or c == '-')

    # Ensure unique
    existing_ids = {f.id for f in backlog.features}
    base_id = feature_id
    counter = 1
    while feature_id in existing_ids:
        feature_id = f"{base_id}-{counter}"
        counter += 1

    feature = Feature(
        id=feature_id,
        name=name,
        description=description,
        category=FeatureCategory(category),
        priority=priority,
        acceptance_criteria=list(criteria),
        depends_on=list(depends_on)
    )

    backlog.features.append(feature)
    backlog_file.write_text(backlog.model_dump_json(indent=2))

    console.print(f"[green]OK[/green] Added feature: {feature_id}")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
def status(project_path: str):
    """Show the status of all features in the backlog."""
    path = Path(project_path)
    backlog_file = path / "feature-list.json"

    if not backlog_file.exists():
        console.print(f"[red]No backlog found at {backlog_file}[/red]")
        return

    backlog = Backlog.model_validate_json(backlog_file.read_text())

    table = Table(title=f"Backlog: {backlog.project_name}")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Priority", justify="right")
    table.add_column("Sessions", justify="right")
    table.add_column("Category")

    status_colors = {
        FeatureStatus.PENDING: "white",
        FeatureStatus.IN_PROGRESS: "yellow",
        FeatureStatus.COMPLETED: "green",
        FeatureStatus.BLOCKED: "red"
    }

    for f in backlog.features:
        color = status_colors.get(f.status, "white")
        table.add_row(
            f.id,
            f.name,
            f"[{color}]{f.status.value}[/{color}]",
            str(f.priority),
            str(f.sessions_spent),
            f.category.value
        )

    console.print(table)

    # Summary
    completed = sum(1 for f in backlog.features if f.status == FeatureStatus.COMPLETED)
    in_progress = sum(1 for f in backlog.features if f.status == FeatureStatus.IN_PROGRESS)
    pending = sum(1 for f in backlog.features if f.status == FeatureStatus.PENDING)

    console.print(f"\n[green]Completed:[/green] {completed}  "
                  f"[yellow]In Progress:[/yellow] {in_progress}  "
                  f"[white]Pending:[/white] {pending}")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--lines', default=50, help='Number of recent lines to show')
def progress(project_path: str, lines: int):
    """Show recent progress from the progress file."""
    path = Path(project_path)
    progress_file = path / "claude-progress.txt"

    if not progress_file.exists():
        console.print("[yellow]No progress file yet. Run 'ada run' to start.[/yellow]")
        return

    content = progress_file.read_text()
    all_lines = content.strip().split('\n')

    if len(all_lines) > lines:
        console.print(f"[dim]... showing last {lines} lines ...[/dim]\n")
        console.print('\n'.join(all_lines[-lines:]))
    else:
        console.print(content)


@main.command('import-backlog')
@click.argument('project_path', type=click.Path(exists=True))
@click.argument('markdown_file', type=click.Path(exists=True))
def import_backlog(project_path: str, markdown_file: str):
    """Import features from a markdown file.

    Parses a markdown file with task lists and converts to feature-list.json.
    Format expected:
    - [ ] Feature name: Description
    - [x] Completed feature: Description
    """
    path = Path(project_path)
    md_path = Path(markdown_file)

    backlog_file = path / "feature-list.json"
    if backlog_file.exists():
        backlog = Backlog.model_validate_json(backlog_file.read_text())
    else:
        backlog = Backlog(
            project_name=path.name,
            project_path=str(path.resolve()),
            features=[]
        )

    content = md_path.read_text()
    imported = 0

    for line in content.split('\n'):
        line = line.strip()

        # Parse markdown task list items
        if line.startswith('- [ ]') or line.startswith('- [x]'):
            completed = line.startswith('- [x]')
            text = line[6:].strip()

            # Split on colon if present
            if ':' in text:
                name, description = text.split(':', 1)
                name = name.strip()
                description = description.strip()
            else:
                name = text
                description = text

            # Generate ID
            feature_id = name.lower().replace(' ', '-')
            feature_id = ''.join(c for c in feature_id if c.isalnum() or c == '-')

            # Check for duplicates
            if any(f.id == feature_id for f in backlog.features):
                continue

            feature = Feature(
                id=feature_id,
                name=name,
                description=description,
                status=FeatureStatus.COMPLETED if completed else FeatureStatus.PENDING
            )
            backlog.features.append(feature)
            imported += 1

    backlog_file.write_text(backlog.model_dump_json(indent=2))
    console.print(f"[green]OK[/green] Imported {imported} features from {markdown_file}")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--to', 'commit_hash', help='Commit hash to reset to')
@click.option('--hard', is_flag=True, help='Hard reset (discard all changes)')
@click.option('--list', 'list_commits', is_flag=True, help='List recent commits')
@click.option('--revert', is_flag=True, help='Revert the last commit (creates new commit)')
def rollback(project_path: str, commit_hash: Optional[str], hard: bool, list_commits: bool, revert: bool):
    """Rollback to a previous commit or revert the last commit.

    Examples:

    \b
    # List recent commits
    ada rollback <path> --list

    \b
    # Revert last commit (safe - creates new commit)
    ada rollback <path> --revert

    \b
    # Reset to specific commit (soft reset - keeps changes staged)
    ada rollback <path> --to abc123

    \b
    # Hard reset (DANGEROUS - discards all changes)
    ada rollback <path> --to abc123 --hard
    """
    path = Path(project_path)
    git = GitManager(path)

    if not git.is_git_repo():
        console.print("[red]Not a git repository[/red]")
        return

    # List recent commits
    if list_commits:
        commits = git.get_recent_commits(count=10)
        if not commits:
            console.print("[yellow]No commits found[/yellow]")
            return

        table = Table(title="Recent Commits")
        table.add_column("Hash", style="cyan")
        table.add_column("Message")

        for hash_, message in commits:
            table.add_row(hash_[:8], message[:60] + "..." if len(message) > 60 else message)

        console.print(table)
        console.print("\n[dim]Use 'ada rollback <path> --to <hash>' to reset[/dim]")
        return

    # Revert last commit
    if revert:
        console.print("[yellow]Reverting last commit...[/yellow]")
        new_hash = git.revert_last_commit()

        if new_hash:
            console.print(f"[green]OK[/green] Created revert commit: {new_hash[:8]}")
        else:
            console.print("[red]Failed to revert. There may be conflicts or no commits to revert.[/red]")
        return

    # Reset to specific commit
    if commit_hash:
        # Verify commit exists
        commit_info = git.get_commit_info(commit_hash)
        if not commit_info:
            console.print(f"[red]Commit not found: {commit_hash}[/red]")
            return

        full_hash, message, date = commit_info

        console.print(f"\n[bold]Target commit:[/bold]")
        console.print(f"  Hash: {full_hash[:8]}")
        console.print(f"  Message: {message}")
        console.print(f"  Date: {date}")

        # Show commits that will be affected
        commits_to_undo = git.get_commits_since(commit_hash)
        if commits_to_undo:
            console.print(f"\n[yellow]{len(commits_to_undo)} commit(s) will be undone:[/yellow]")
            for hash_, msg in commits_to_undo[:5]:
                console.print(f"  - {hash_[:8]}: {msg[:50]}")
            if len(commits_to_undo) > 5:
                console.print(f"  ... and {len(commits_to_undo) - 5} more")

        mode_text = "[red]HARD (changes will be LOST)[/red]" if hard else "soft (changes will be staged)"
        console.print(f"\n[bold]Reset mode:[/bold] {mode_text}")

        # Confirm for hard reset
        if hard:
            if not click.confirm("\nThis will permanently delete uncommitted changes. Continue?"):
                console.print("[yellow]Cancelled[/yellow]")
                return

        if git.reset_to_commit(commit_hash, hard=hard):
            console.print(f"\n[green]OK[/green] Reset to {full_hash[:8]}")
            if not hard:
                console.print("[dim]Changes from undone commits are now staged[/dim]")
        else:
            console.print("[red]Reset failed[/red]")
        return

    # No options specified - show help
    console.print("Usage: ada rollback <path> [OPTIONS]")
    console.print("\nOptions:")
    console.print("  --list    List recent commits")
    console.print("  --revert  Revert the last commit (safe)")
    console.print("  --to      Reset to a specific commit")
    console.print("  --hard    Hard reset (use with --to)")
    console.print("\nRun 'ada rollback --help' for more info")


if __name__ == '__main__':
    main()

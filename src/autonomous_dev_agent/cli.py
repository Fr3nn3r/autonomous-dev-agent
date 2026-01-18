"""CLI interface for the Autonomous Development Agent."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .models import (
    Backlog, Feature, FeatureStatus, FeatureCategory, HarnessConfig, SessionMode,
    Severity, DiscoveryResult, VerificationConfig,
)
from .harness import AutonomousHarness
from .git_manager import GitManager
from .discovery import (
    CodebaseAnalyzer, BestPracticesChecker, TestGapAnalyzer,
    DiscoveryTracker, BacklogGenerator,
)
from .discovery.reviewer import CodeReviewer
from .discovery.requirements import RequirementsExtractor
from .verification import FeatureVerifier, PreCompleteHook

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
@click.option('--model', default='claude-sonnet-4-20250514', help='Claude model to use')
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


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--review', is_flag=True, help='Include Claude AI code review (uses API)')
@click.option('--fix', is_flag=True, help='Generate backlog and optionally start fixing')
@click.option('--dry-run', is_flag=True, help='Preview without saving changes')
@click.option('--incremental', is_flag=True, help='Only show new issues since last run')
@click.option('--model', default='claude-sonnet-4-20250514', help='Claude model for AI review')
@click.option('--output', default='feature-list.json', help='Output backlog filename')
def discover(
    project_path: str,
    review: bool,
    fix: bool,
    dry_run: bool,
    incremental: bool,
    model: str,
    output: str,
):
    """Analyze an existing project and discover work to be done.

    Performs static analysis to identify:
    - Missing tests
    - Best practice violations
    - Code structure issues

    \b
    Examples:
      ada discover .                    # Basic static analysis (free)
      ada discover . --review           # Include AI code review
      ada discover . --fix              # Generate backlog from findings
      ada discover . --dry-run          # Preview without saving
      ada discover . --incremental      # Only new issues since last run
    """
    path = Path(project_path).resolve()

    console.print(f"\n[bold]Discovering issues in:[/bold] {path}")
    console.print("")

    # Initialize tracker for incremental mode
    tracker = DiscoveryTracker(path)

    # Phase 1: Static codebase analysis
    with console.status("[bold blue]Analyzing codebase structure..."):
        analyzer = CodebaseAnalyzer(path)
        summary = analyzer.analyze()

    console.print("[green]OK[/green] Codebase analysis complete")
    console.print(f"  Languages: {', '.join(summary.languages) or 'None detected'}")
    console.print(f"  Frameworks: {', '.join(summary.frameworks) or 'None detected'}")
    console.print(f"  Lines of code: {summary.line_counts.get('code', 0):,}")
    console.print(f"  Lines of tests: {summary.line_counts.get('tests', 0):,}")
    console.print("")

    # Phase 2: Best practices check
    with console.status("[bold blue]Checking best practices..."):
        bp_checker = BestPracticesChecker(path, languages=summary.languages)
        violations = bp_checker.check_all()

    console.print(f"[green]OK[/green] Best practices check: {len(violations)} issue(s)")

    # Phase 3: Test gap analysis
    with console.status("[bold blue]Analyzing test coverage gaps..."):
        test_analyzer = TestGapAnalyzer(path, languages=summary.languages)
        test_gaps = test_analyzer.analyze()

    console.print(f"[green]OK[/green] Test gap analysis: {len(test_gaps)} gap(s)")

    # Phase 4: Code review (optional, uses AI)
    code_issues = []
    if review:
        console.print("")
        with console.status("[bold blue]Running AI code review (this may take a minute)..."):
            reviewer = CodeReviewer(path, model=model)
            code_issues = reviewer.review_sync()

        console.print(f"[green]OK[/green] AI code review: {len(code_issues)} issue(s)")

    # Build discovery result
    result = DiscoveryResult(
        project_path=str(path),
        summary=summary,
        code_issues=code_issues,
        test_gaps=test_gaps,
        best_practice_violations=violations,
    )

    # Apply incremental filtering if requested
    if incremental:
        original_count = result.total_issues()
        result = tracker.filter_new_issues(result)
        filtered_count = result.total_issues()
        console.print(f"\n[dim]Incremental mode: showing {filtered_count} new issues (filtered {original_count - filtered_count} known)[/dim]")

    # Display results
    console.print("\n" + "=" * 60)
    console.print("[bold]Discovery Results[/bold]")
    console.print("=" * 60)

    # Summary by severity
    severity_counts = result.issues_by_severity()
    console.print(f"\n[red]Critical:[/red] {severity_counts[Severity.CRITICAL]}  "
                  f"[yellow]High:[/yellow] {severity_counts[Severity.HIGH]}  "
                  f"[blue]Medium:[/blue] {severity_counts[Severity.MEDIUM]}  "
                  f"[dim]Low:[/dim] {severity_counts[Severity.LOW]}")

    # Show issues by category
    if code_issues:
        console.print("\n[bold]Code Issues:[/bold]")
        _display_code_issues(code_issues[:10])  # Show top 10
        if len(code_issues) > 10:
            console.print(f"  [dim]... and {len(code_issues) - 10} more[/dim]")

    if test_gaps:
        console.print("\n[bold]Test Gaps:[/bold]")
        _display_test_gaps(test_gaps[:10])
        if len(test_gaps) > 10:
            console.print(f"  [dim]... and {len(test_gaps) - 10} more[/dim]")

    if violations:
        console.print("\n[bold]Best Practice Issues:[/bold]")
        _display_violations(violations[:10])
        if len(violations) > 10:
            console.print(f"  [dim]... and {len(violations) - 10} more[/dim]")

    # Generate backlog if requested
    if fix and not dry_run:
        console.print("\n" + "-" * 60)
        console.print("[bold]Generating backlog...[/bold]")

        # Check for existing backlog
        backlog_path = path / output
        existing_backlog = None
        if backlog_path.exists():
            try:
                existing_backlog = Backlog.model_validate_json(backlog_path.read_text())
                console.print(f"  Found existing backlog with {len(existing_backlog.features)} features")
            except Exception:
                pass

        generator = BacklogGenerator(path)
        backlog = generator.generate(result, existing_backlog=existing_backlog)

        # Save backlog
        output_path = generator.save_backlog(backlog, filename=output)
        console.print(f"[green]OK[/green] Saved {len(backlog.features)} features to {output_path}")

        # Update tracker state
        tracker.update_from_result(result)
        tracker.save_state()
        console.print("[green]OK[/green] Updated discovery state")

    elif fix and dry_run:
        console.print("\n[yellow]Dry run:[/yellow] Would generate backlog with findings")

    # Save tracker state even without --fix (for incremental mode)
    if not dry_run and not fix:
        tracker.mark_issues_known(result)
        tracker.save_state()

    # Final summary
    console.print("\n" + "=" * 60)
    total = result.total_issues()
    if total == 0:
        console.print("[green]No issues found! The codebase looks good.[/green]")
    else:
        console.print(f"[bold]Total: {total} issue(s) discovered[/bold]")
        if not fix:
            console.print("\n[dim]Run with --fix to generate a backlog from these findings[/dim]")


def _display_code_issues(issues: list) -> None:
    """Display code issues in a formatted way."""
    severity_colors = {
        Severity.CRITICAL: "red",
        Severity.HIGH: "yellow",
        Severity.MEDIUM: "blue",
        Severity.LOW: "dim",
    }

    for issue in issues:
        color = severity_colors.get(issue.severity, "white")
        location = f"{issue.file}"
        if issue.line:
            location += f":{issue.line}"
        console.print(f"  [{color}]{issue.severity.value.upper()}[/{color}] {issue.title}")
        console.print(f"    [dim]{location}[/dim]")


def _display_test_gaps(gaps: list) -> None:
    """Display test gaps in a formatted way."""
    for gap in gaps:
        critical_marker = " [red](critical path)[/red]" if gap.is_critical_path else ""
        console.print(f"  {gap.module}{critical_marker}")
        console.print(f"    [dim]{gap.gap_type.replace('_', ' ')}[/dim]")


def _display_violations(violations: list) -> None:
    """Display best practice violations."""
    for v in violations:
        console.print(f"  [{v.severity.value}] {v.title}")
        console.print(f"    [dim]{v.recommendation}[/dim]")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=8000, help='Port to listen on')
@click.option('--reload', is_flag=True, help='Enable auto-reload for development')
def dashboard(project_path: str, host: str, port: int, reload: bool):
    """Start the dashboard server for real-time monitoring.

    Starts a FastAPI server that provides:
    - REST API at http://host:port/api/
    - WebSocket at ws://host:port/ws/events
    - API docs at http://host:port/docs

    The dashboard reads project state files and provides real-time
    updates via WebSocket when files change.

    Example:
        ada dashboard ./my-project --port 8000
    """
    from .api import run_dashboard

    path = Path(project_path)
    console.print(f"[bold]Starting ADA Dashboard[/bold]")
    console.print(f"Project: {path}")
    console.print(f"API: http://{host}:{port}/api/")
    console.print(f"Docs: http://{host}:{port}/docs")
    console.print(f"WebSocket: ws://{host}:{port}/ws/events")
    console.print(f"\nPress Ctrl+C to stop\n")

    try:
        run_dashboard(path, host=host, port=port, reload=reload)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped[/yellow]")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
def costs(project_path: str):
    """Show cost summary for the project.

    Displays total costs, token usage, and breakdowns by model and outcome.
    """
    from .session_history import SessionHistory
    from .cost_tracker import CostTracker

    path = Path(project_path)
    history = SessionHistory(path)

    summary = history.get_cost_summary()

    if summary.total_sessions == 0:
        console.print("[yellow]No sessions recorded yet.[/yellow]")
        return

    # Header
    console.print(f"\n[bold]Cost Summary for {path.name}[/bold]\n")

    # Totals table
    from rich.table import Table

    totals_table = Table(title="Totals", show_header=False)
    totals_table.add_column("Metric", style="cyan")
    totals_table.add_column("Value", style="green")

    totals_table.add_row("Total Cost", f"${summary.total_cost_usd:.4f}")
    totals_table.add_row("Total Sessions", str(summary.total_sessions))
    totals_table.add_row("Input Tokens", CostTracker.format_tokens(summary.total_input_tokens))
    totals_table.add_row("Output Tokens", CostTracker.format_tokens(summary.total_output_tokens))
    if summary.total_cache_read_tokens:
        totals_table.add_row("Cache Read", CostTracker.format_tokens(summary.total_cache_read_tokens))

    console.print(totals_table)

    # Cost by model
    if summary.cost_by_model:
        console.print("\n[bold]By Model[/bold]")
        model_table = Table()
        model_table.add_column("Model", style="cyan")
        model_table.add_column("Sessions", justify="right")
        model_table.add_column("Cost", justify="right", style="green")

        for model, cost in sorted(summary.cost_by_model.items(), key=lambda x: -x[1]):
            sessions = summary.sessions_by_model.get(model, 0)
            model_table.add_row(model, str(sessions), f"${cost:.4f}")

        console.print(model_table)

    # Sessions by outcome
    if summary.sessions_by_outcome:
        console.print("\n[bold]By Outcome[/bold]")
        outcome_table = Table()
        outcome_table.add_column("Outcome", style="cyan")
        outcome_table.add_column("Sessions", justify="right")

        outcome_colors = {
            "success": "green",
            "failure": "red",
            "handoff": "yellow",
            "timeout": "red",
        }

        for outcome, count in sorted(summary.sessions_by_outcome.items()):
            color = outcome_colors.get(outcome, "white")
            outcome_table.add_row(f"[{color}]{outcome}[/{color}]", str(count))

        console.print(outcome_table)


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--feature', '-f', help='Specific feature ID to verify (default: all in_progress)')
@click.option('--test-command', help='Unit test command (e.g., "npm test", "pytest")')
@click.option('--e2e-command', help='E2E test command (e.g., "npx playwright test")')
@click.option('--lint-command', help='Lint command (e.g., "npm run lint", "ruff check .")')
@click.option('--type-check', help='Type check command (e.g., "npm run typecheck", "mypy .")')
@click.option('--coverage-command', help='Coverage command (e.g., "npm run test:coverage")')
@click.option('--coverage-threshold', type=float, help='Minimum coverage percentage')
@click.option('--require-approval', is_flag=True, help='Require manual approval')
@click.option('--dry-run', is_flag=True, help='Show what would be verified without running')
def verify(
    project_path: str,
    feature: Optional[str],
    test_command: Optional[str],
    e2e_command: Optional[str],
    lint_command: Optional[str],
    type_check: Optional[str],
    coverage_command: Optional[str],
    coverage_threshold: Optional[float],
    require_approval: bool,
    dry_run: bool
):
    """Run verification checks on features.

    Runs comprehensive verification including tests, linting, type checking,
    coverage analysis, and optional manual approval.

    \b
    Examples:
      ada verify .                           # Verify all in_progress features
      ada verify . -f my-feature             # Verify specific feature
      ada verify . --test-command "pytest"   # Use custom test command
      ada verify . --require-approval        # Require manual approval
      ada verify . --dry-run                 # Preview without running
    """
    path = Path(project_path)
    backlog_file = path / "feature-list.json"

    if not backlog_file.exists():
        console.print(f"[red]No backlog found at {backlog_file}[/red]")
        return

    backlog = Backlog.model_validate_json(backlog_file.read_text())

    # Build verification config from options
    config = VerificationConfig(
        test_command=test_command or "npm test",
        e2e_command=e2e_command,
        lint_command=lint_command,
        type_check_command=type_check,
        coverage_command=coverage_command,
        coverage_threshold=coverage_threshold,
        require_manual_approval=require_approval,
    )

    # Get features to verify
    if feature:
        features_to_verify = [f for f in backlog.features if f.id == feature]
        if not features_to_verify:
            console.print(f"[red]Feature not found: {feature}[/red]")
            return
    else:
        features_to_verify = [f for f in backlog.features if f.status == FeatureStatus.IN_PROGRESS]
        if not features_to_verify:
            console.print("[yellow]No in_progress features to verify[/yellow]")
            console.print("[dim]Use -f <feature_id> to verify a specific feature[/dim]")
            return

    console.print(f"\n[bold]Verifying {len(features_to_verify)} feature(s)[/bold]\n")

    if dry_run:
        console.print("[yellow]Dry run - showing configuration:[/yellow]")
        console.print(f"  Test command: {config.test_command}")
        console.print(f"  E2E command: {config.e2e_command or 'Not configured'}")
        console.print(f"  Lint command: {config.lint_command or 'Not configured'}")
        console.print(f"  Type check: {config.type_check_command or 'Not configured'}")
        console.print(f"  Coverage: {config.coverage_command or 'Not configured'}")
        if config.coverage_threshold:
            console.print(f"  Coverage threshold: {config.coverage_threshold}%")
        console.print(f"  Manual approval: {'Required' if config.require_manual_approval else 'Not required'}")
        console.print(f"\nFeatures to verify:")
        for f in features_to_verify:
            console.print(f"  - {f.id}: {f.name}")
        return

    verifier = FeatureVerifier(path, config)

    # Verify each feature
    for feat in features_to_verify:
        console.print(f"\n{'=' * 60}")
        console.print(f"[bold]Verifying: {feat.name}[/bold]")
        console.print(f"[dim]{feat.description}[/dim]")
        console.print("=" * 60)

        report = verifier.verify(feat, interactive=True)

        # Display results
        for r in report.results:
            if r.skipped:
                console.print(f"  [dim]⊘ {r.name}: {r.message}[/dim]")
            elif r.passed:
                duration_str = f" ({r.duration_seconds:.1f}s)" if r.duration_seconds else ""
                console.print(f"  [green]✓[/green] {r.name}: {r.message}{duration_str}")
            else:
                console.print(f"  [red]✗[/red] {r.name}: {r.message}")
                if r.details:
                    details = r.details[:300] + "..." if len(r.details) > 300 else r.details
                    console.print(f"    [dim]{details}[/dim]")

        # Show coverage
        if report.coverage:
            console.print(f"\n  [bold]Coverage:[/bold] {report.coverage.coverage_percent:.1f}%")

        # Summary
        if report.passed:
            approval_note = " (approved)" if report.requires_approval and report.approved else ""
            console.print(f"\n  [green]✓ Verification passed{approval_note}[/green]")
        else:
            console.print(f"\n  [red]✗ Verification failed[/red]")


@main.command('init-hooks')
@click.argument('project_path', type=click.Path(exists=True))
def init_hooks(project_path: str):
    """Create sample pre-complete hook scripts.

    Creates a sample hook script in .ada/hooks/ that you can customize.
    The hook runs before any feature is marked complete.
    """
    path = Path(project_path)

    hook_runner = PreCompleteHook(path)
    hook_path = hook_runner.create_sample_hook()

    console.print(f"[green]OK[/green] Created sample hook at: {hook_path}")
    console.print(f"\nEdit this file to add your custom validation logic.")
    console.print(f"The hook receives these environment variables:")
    console.print(f"  ADA_PROJECT_PATH - Project root path")
    console.print(f"  ADA_FEATURE_ID - Feature being completed")
    console.print(f"  ADA_FEATURE_NAME - Feature name")
    console.print(f"  ADA_FEATURE_CATEGORY - Feature category")
    console.print(f"\nExit with 0 to allow completion, non-zero to block.")


if __name__ == '__main__':
    main()

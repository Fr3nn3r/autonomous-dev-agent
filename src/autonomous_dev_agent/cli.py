"""CLI interface for the Autonomous Development Agent."""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .models import (
    Backlog, Feature, FeatureStatus, FeatureCategory, HarnessConfig,
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
from .generation import SpecParser, FeatureGenerator, GenerationError
from .workspace import WorkspaceManager
from .log_formatter import (
    format_session_list, format_session_detail, stream_session_pretty,
    format_workspace_info, export_sessions_to_jsonl, format_duration, format_tokens
)

console = Console()

# Windows-compatible symbols (cp1252 doesn't support Unicode checkmarks)
if sys.platform == "win32":
    SYM_OK = "[OK]"
    SYM_FAIL = "[X]"
else:
    SYM_OK = "✓"
    SYM_FAIL = "✗"


@click.group()
@click.version_option()
def main():
    """Autonomous Development Agent - Long-running coding agent harness."""
    pass


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--model', default='claude-opus-4-5-20251101', help='Claude model to use')
@click.option('--threshold', default=70.0, help='Context threshold percentage for handoff')
@click.option('--max-sessions', type=int, help='Maximum sessions before stopping')
@click.option('--backlog', default='feature-list.json', help='Backlog file name')
def run(
    project_path: str,
    model: str,
    threshold: float,
    max_sessions: Optional[int],
    backlog: str,
):
    """Run the autonomous agent on a project.

    PROJECT_PATH is the path to the project directory containing feature-list.json.

    Uses the Claude Agent SDK with API credits for billing. Provides real-time
    streaming output and detailed observability.
    """
    config = HarnessConfig(
        model=model,
        context_threshold_percent=threshold,
        max_sessions=max_sessions,
        backlog_file=backlog
    )

    console.print(f"[bold]Mode:[/bold] SDK (API credits)")
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
@click.option('--description', default='', help='Project description (prompted if not provided)')
@click.option('--spec', type=click.Path(exists=True), help='Specification file to generate features from')
@click.option('--model', default='claude-opus-4-5-20251101', help='Claude model for spec generation')
@click.option('--max-features', default=50, help='Maximum features to generate from spec')
@click.option('--min-features', default=20, help='Minimum features to generate from spec')
def init(
    project_path: str,
    name: str,
    description: str,
    spec: Optional[str],
    model: str,
    max_features: int,
    min_features: int
):
    """Initialize a new project for autonomous development.

    Creates the feature-list.json, .ada/ directory structure, and project.json.

    \b
    Examples:
        ada init ./my-project --name "My App"
        ada init ./my-project --name "My App" --spec ./spec.md
        ada init ./my-project --name "My App" --spec ./spec.md --max-features 30

    When --spec is provided, Claude AI analyzes the specification file and
    generates a feature backlog automatically.
    """
    path = Path(project_path)
    path.mkdir(parents=True, exist_ok=True)

    # Prompt for description if not provided
    if not description:
        description = click.prompt(
            'Project description (optional, press Enter to skip)',
            default='',
            show_default=False
        )

    backlog_file = path / "feature-list.json"

    # Generate features from spec if provided
    if spec:
        console.print(f"\n[bold]Generating features from specification...[/bold]")
        console.print(f"  Spec file: {spec}")
        console.print(f"  Model: {model}")
        console.print(f"  Feature range: {min_features}-{max_features}")
        console.print("")

        try:
            generator = FeatureGenerator(
                model=model,
                min_features=min_features,
                max_features=max_features,
            )
            result = generator.generate_from_file(
                spec_path=spec,
                project_name=name,
                project_path=path,
            )

            backlog = result.backlog
            console.print(f"[green]OK[/green] Generated {result.feature_count} features")

            # Build init_session info for project.json
            init_session_info = {
                "spec_file": str(Path(spec).resolve()),
                "model": model,
                "feature_count": result.feature_count,
                "outcome": "success",
                "generated_at": datetime.now().isoformat()
            }

        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            return
        except ValueError as e:
            console.print(f"[red]Validation error:[/red] {e}")
            return
        except RuntimeError as e:
            console.print(f"[red]Generation error:[/red] {e}")
            return
    else:
        # Create empty backlog
        backlog = Backlog(
            project_name=name,
            project_path=str(path.resolve()),
            features=[]
        )
        init_session_info = None

    # Save backlog
    if backlog_file.exists():
        console.print(f"[yellow]Backlog already exists at {backlog_file}[/yellow]")
        if spec and click.confirm("Overwrite with generated features?"):
            backlog_file.write_text(backlog.model_dump_json(indent=2))
            console.print(f"[green]OK[/green] Updated {backlog_file}")
    else:
        backlog_file.write_text(backlog.model_dump_json(indent=2))
        console.print(f"[green]OK[/green] Created {backlog_file}")

    # Create .ada/ workspace structure
    workspace = WorkspaceManager(path)
    workspace.ensure_structure()

    # Create project.json
    if not workspace.project_file.exists():
        workspace.create_project_context(
            name=name,
            description=description,
            created_by="user",
            init_session=init_session_info
        )
        console.print(f"[green]OK[/green] Created .ada/project.json")
    else:
        console.print(f"[yellow]project.json already exists[/yellow]")

    # Update .gitignore
    if workspace.update_gitignore():
        console.print(f"[green]OK[/green] Updated .gitignore")

    console.print(f"\nNext steps:")
    if spec:
        console.print(f"  1. Review generated features: ada status {project_path}")
    else:
        console.print(f"  1. Add features: ada add-feature {project_path} --name 'Feature name'")
    console.print(f"  2. Run agent: ada run {project_path}")
    console.print(f"  3. View project info: ada info {project_path}")


@main.command('generate-backlog')
@click.argument('spec_file', type=click.Path(exists=True))
@click.option('--project-path', '-p', type=click.Path(), default='.',
              help='Project directory (default: current directory)')
@click.option('--project-name', '-n', help='Project name (default: derived from spec)')
@click.option('--max-features', default=50, help='Maximum features to generate')
@click.option('--min-features', default=20, help='Minimum features to generate')
@click.option('--model', default='claude-opus-4-5-20251101', help='Claude model to use')
@click.option('--output', '-o', default='feature-list.json', help='Output filename')
@click.option('--merge', is_flag=True, help='Merge with existing backlog')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--verbose', '-v', is_flag=True, help='Show raw Claude response on error')
def generate_backlog(
    spec_file: str,
    project_path: str,
    project_name: Optional[str],
    max_features: int,
    min_features: int,
    model: str,
    output: str,
    merge: bool,
    dry_run: bool,
    verbose: bool,
):
    """Generate a feature backlog from a specification file using Claude AI.

    Analyzes the specification and generates a structured feature backlog
    with priorities, acceptance criteria, and implementation steps.

    \b
    Examples:
        ada generate-backlog ./spec.md
        ada generate-backlog ./spec.md -p ./my-project -n "My App"
        ada generate-backlog ./spec.md --max-features 30 --dry-run
        ada generate-backlog ./spec.md --merge  # Merge with existing backlog

    Supported file types: .txt, .md, .spec, .markdown
    """
    path = Path(project_path).resolve()
    spec_path = Path(spec_file).resolve()

    console.print(f"\n[bold]Generating Feature Backlog[/bold]")
    console.print(f"  Spec: {spec_path.name}")
    console.print(f"  Model: {model}")
    console.print(f"  Features: {min_features}-{max_features}")
    if dry_run:
        console.print(f"  [yellow]DRY RUN - no files will be saved[/yellow]")
    console.print("")

    # Validate spec file
    is_valid, error = SpecParser.validate_path(spec_path)
    if not is_valid:
        console.print(f"[red]Invalid spec file:[/red] {error}")
        return

    # Generate features
    with console.status("[bold blue]Analyzing specification with Claude AI..."):
        try:
            generator = FeatureGenerator(
                model=model,
                min_features=min_features,
                max_features=max_features,
            )
            result = generator.generate_from_file(
                spec_path=spec_path,
                project_name=project_name,
                project_path=path,
            )
        except GenerationError as e:
            console.print(f"[red]Generation failed:[/red] {e}")
            if verbose and e.raw_response:
                console.print("\n[yellow]Raw Claude response:[/yellow]")
                console.print(e.raw_response)
            elif not verbose and e.raw_response:
                console.print("[dim]Use --verbose to see raw Claude response[/dim]")
            return
        except RuntimeError as e:
            console.print(f"[red]Generation failed:[/red] {e}")
            return
        except ValueError as e:
            console.print(f"[red]Validation error:[/red] {e}")
            return

    console.print(f"[green]OK[/green] Generated {result.feature_count} features")
    console.print("")

    # Show feature summary
    table = Table(title="Generated Features")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Priority", justify="right")
    table.add_column("Dependencies")

    for f in result.backlog.features[:20]:  # Show first 20
        deps = ", ".join(f.depends_on) if f.depends_on else "-"
        table.add_row(
            f.id,
            f.name[:40] + "..." if len(f.name) > 40 else f.name,
            f.category.value,
            str(f.priority),
            deps[:20] + "..." if len(deps) > 20 else deps
        )

    if result.feature_count > 20:
        table.add_row("...", f"[dim]and {result.feature_count - 20} more[/dim]", "", "", "")

    console.print(table)

    if dry_run:
        console.print("\n[yellow]Dry run complete - no files saved[/yellow]")
        return

    # Handle merge with existing backlog
    output_path = path / output
    backlog_to_save = result.backlog

    if output_path.exists():
        if merge:
            try:
                existing = Backlog.model_validate_json(output_path.read_text())
                backlog_to_save = generator.merge_with_existing(result, existing)
                new_count = len(backlog_to_save.features) - len(existing.features)
                console.print(f"\n[green]OK[/green] Merged with existing backlog (+{new_count} new features)")
            except Exception as e:
                console.print(f"[red]Failed to merge:[/red] {e}")
                return
        else:
            if not click.confirm(f"\n{output} already exists. Overwrite?"):
                console.print("[yellow]Cancelled[/yellow]")
                return

    # Save backlog
    output_path.write_text(backlog_to_save.model_dump_json(indent=2))
    console.print(f"\n[green]OK[/green] Saved {len(backlog_to_save.features)} features to {output_path}")

    # Next steps
    console.print(f"\nNext steps:")
    console.print(f"  1. Review features: ada status {project_path}")
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
@click.option('--reason', '-r', default='Stop requested via CLI', help='Reason for stopping')
@click.option('--cancel', is_flag=True, help='Cancel a pending stop request')
@click.option('--status', 'show_status', is_flag=True, help='Check if stop is pending')
def stop(project_path: str, reason: str, cancel: bool, show_status: bool):
    """Request graceful shutdown of a running agent.

    Creates a stop signal that the agent checks after each tool call.
    The agent will finish current work, commit changes, and exit cleanly.

    \b
    Examples:
        ada stop ./my-project                    # Request stop
        ada stop ./my-project -r "Lunch break"   # Stop with reason
        ada stop ./my-project --status           # Check if stop pending
        ada stop ./my-project --cancel           # Cancel pending stop
    """
    path = Path(project_path)
    stop_file = path / ".ada" / "stop-requested"

    if show_status:
        if stop_file.exists():
            content = stop_file.read_text().strip().split('\n')
            timestamp = content[0] if content else "unknown"
            stop_reason = content[1] if len(content) > 1 else "No reason given"
            console.print(f"[yellow]Stop request pending[/yellow]")
            console.print(f"  Requested at: {timestamp}")
            console.print(f"  Reason: {stop_reason}")
        else:
            console.print("[green]No stop request pending[/green]")
        return

    if cancel:
        if stop_file.exists():
            stop_file.unlink()
            console.print("[green]OK[/green] Stop request cancelled")
        else:
            console.print("[yellow]No stop request was pending[/yellow]")
        return

    # Create stop request
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text(f"{datetime.now().isoformat()}\n{reason}")

    console.print("[green]OK[/green] Stop request sent")
    console.print(f"  Stop file: {stop_file}")
    console.print(f"  Reason: {reason}")
    console.print("\n[dim]The agent will stop after completing its current operation.[/dim]")
    console.print("[dim]Use 'ada stop <path> --status' to check progress.[/dim]")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--review', is_flag=True, help='Include Claude AI code review (uses API)')
@click.option('--fix', is_flag=True, help='Generate backlog and optionally start fixing')
@click.option('--dry-run', is_flag=True, help='Preview without saving changes')
@click.option('--incremental', is_flag=True, help='Only show new issues since last run')
@click.option('--model', default='claude-opus-4-5-20251101', help='Claude model for AI review')
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
def tokens(project_path: str):
    """Show token consumption summary for the project.

    Displays total token usage and breakdowns by model and outcome.
    """
    from .session_history import SessionHistory
    from .token_tracker import format_tokens as fmt_tokens

    path = Path(project_path)
    history = SessionHistory(path)

    summary = history.get_token_summary()

    if summary.total_sessions == 0:
        console.print("[yellow]No sessions recorded yet.[/yellow]")
        return

    # Header
    console.print(f"\n[bold]Token Consumption for {path.name}[/bold]\n")

    # Totals table
    from rich.table import Table

    totals_table = Table(title="Totals", show_header=False)
    totals_table.add_column("Metric", style="cyan")
    totals_table.add_column("Value", style="green")

    totals_table.add_row("Total Sessions", str(summary.total_sessions))
    totals_table.add_row("Total Tokens", fmt_tokens(summary.total_tokens))
    totals_table.add_row("Input Tokens", fmt_tokens(summary.total_input_tokens))
    totals_table.add_row("Output Tokens", fmt_tokens(summary.total_output_tokens))
    if summary.total_cache_read_tokens:
        totals_table.add_row("Cache Read", fmt_tokens(summary.total_cache_read_tokens))
    if summary.total_cache_write_tokens:
        totals_table.add_row("Cache Write", fmt_tokens(summary.total_cache_write_tokens))

    console.print(totals_table)

    # Tokens by model
    if summary.tokens_by_model:
        console.print("\n[bold]By Model[/bold]")
        model_table = Table()
        model_table.add_column("Model", style="cyan")
        model_table.add_column("Sessions", justify="right")
        model_table.add_column("Tokens", justify="right", style="green")

        for model, tokens_count in sorted(summary.tokens_by_model.items(), key=lambda x: -x[1]):
            sessions = summary.sessions_by_model.get(model, 0)
            model_table.add_row(model, str(sessions), fmt_tokens(tokens_count))

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
                console.print(f"  [dim][-] {r.name}: {r.message}[/dim]")
            elif r.passed:
                duration_str = f" ({r.duration_seconds:.1f}s)" if r.duration_seconds else ""
                console.print(f"  [green]{SYM_OK}[/green] {r.name}: {r.message}{duration_str}")
            else:
                console.print(f"  [red]{SYM_FAIL}[/red] {r.name}: {r.message}")
                if r.details:
                    details = r.details[:300] + "..." if len(r.details) > 300 else r.details
                    console.print(f"    [dim]{details}[/dim]")

        # Show coverage
        if report.coverage:
            console.print(f"\n  [bold]Coverage:[/bold] {report.coverage.coverage_percent:.1f}%")

        # Summary
        if report.passed:
            approval_note = " (approved)" if report.requires_approval and report.approved else ""
            console.print(f"\n  [green]{SYM_OK} Verification passed{approval_note}[/green]")
        else:
            console.print(f"\n  [red]{SYM_FAIL} Verification failed[/red]")


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


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
def migrate(project_path: str):
    """Migrate an existing project to the new .ada/ workspace structure.

    Moves legacy state files to their new locations:
    - .ada_session_state.json -> .ada/state/session.json
    - .ada_session_history.json -> .ada/state/history.json
    - .ada_alerts.json -> .ada/alerts.json

    Also creates project.json from the backlog's project_name.

    Example:
        ada migrate ./my-project
    """
    path = Path(project_path)
    workspace = WorkspaceManager(path)

    console.print(f"\n[bold]Migrating project to new workspace structure[/bold]\n")

    # Check what needs migration
    legacy_state = workspace.get_legacy_state_file()
    legacy_history = workspace.get_legacy_history_file()
    legacy_alerts = workspace.get_legacy_alerts_file()

    if not any([legacy_state, legacy_history, legacy_alerts]) and workspace.exists():
        console.print("[green]Project already uses new workspace structure.[/green]")
        return

    # Create workspace structure
    workspace.ensure_structure()
    console.print(f"[green]OK[/green] Created .ada/ directory structure")

    # Migrate files
    results = workspace.migrate_legacy_files()

    for file_type, success in results.items():
        if success:
            console.print(f"[green]OK[/green] Migrated {file_type}")
        else:
            console.print(f"[red]Failed[/red] Could not migrate {file_type}")

    # Create project.json from backlog if it doesn't exist
    if not workspace.project_file.exists():
        backlog_file = path / "feature-list.json"
        if backlog_file.exists():
            try:
                backlog = Backlog.model_validate_json(backlog_file.read_text())
                workspace.create_project_context(
                    name=backlog.project_name,
                    description="",
                    created_by="migration"
                )
                console.print(f"[green]OK[/green] Created project.json from backlog")
            except Exception as e:
                console.print(f"[yellow]Warning[/yellow] Could not read backlog: {e}")

    # Update .gitignore
    if workspace.update_gitignore():
        console.print(f"[green]OK[/green] Updated .gitignore")

    console.print(f"\n[green]Migration complete![/green]")
    console.print(f"You can safely delete the old .ada_* files after verifying the migration.")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
def info(project_path: str):
    """Display project information and statistics.

    Shows project metadata, session counts, token usage, and log usage.

    Example:
        ada info ./my-project
    """
    path = Path(project_path)
    workspace = WorkspaceManager(path)

    if not workspace.exists():
        console.print("[yellow]No .ada/ workspace found. Run 'ada init' or 'ada migrate' first.[/yellow]")
        return

    # Get workspace stats
    stats = workspace.get_workspace_stats()

    # Get feature stats from backlog
    backlog_file = path / "feature-list.json"
    if backlog_file.exists():
        try:
            backlog = Backlog.model_validate_json(backlog_file.read_text())
            completed = sum(1 for f in backlog.features if f.status == FeatureStatus.COMPLETED)
            in_progress = sum(1 for f in backlog.features if f.status == FeatureStatus.IN_PROGRESS)
            pending = sum(1 for f in backlog.features if f.status == FeatureStatus.PENDING)
            stats["features_total"] = len(backlog.features)
            stats["features_completed"] = completed
            stats["features_in_progress"] = in_progress
            stats["features_pending"] = pending
        except Exception:
            pass

    # Display formatted info
    renderables = format_workspace_info(stats)
    for r in renderables:
        console.print(r)

    # Add feature summary if available
    if "features_total" in stats:
        console.print()
        console.print("[bold]Features:[/bold]")
        console.print(
            f"  [green]Completed:[/green] {stats['features_completed']}  "
            f"[yellow]In Progress:[/yellow] {stats['features_in_progress']}  "
            f"[white]Pending:[/white] {stats['features_pending']}  "
            f"(Total: {stats['features_total']})"
        )


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--session', 'session_id', help='View specific session by ID')
@click.option('--feature', 'feature_id', help='Filter by feature ID')
@click.option('--outcome', type=click.Choice(['success', 'failure', 'handoff', 'timeout']),
              help='Filter by outcome')
@click.option('--since', help='Filter by date (YYYY-MM-DD)')
@click.option('--errors', is_flag=True, help='Only show sessions with errors')
@click.option('--tail', is_flag=True, help='Follow current session in real-time')
@click.option('--format', 'output_format', type=click.Choice(['pretty', 'json']),
              default='pretty', help='Output format')
@click.option('--export', 'export_file', type=click.Path(), help='Export to file')
@click.option('--limit', default=20, help='Maximum sessions to show')
def logs(
    project_path: str,
    session_id: Optional[str],
    feature_id: Optional[str],
    outcome: Optional[str],
    since: Optional[str],
    errors: bool,
    tail: bool,
    output_format: str,
    export_file: Optional[str],
    limit: int
):
    """View session logs.

    List recent sessions or view a specific session's details.

    \b
    Examples:
        ada logs ./my-project                    # List recent sessions
        ada logs ./my-project --session 20240115_001  # View specific session
        ada logs ./my-project --feature user-auth     # Filter by feature
        ada logs ./my-project --outcome failure       # Filter by outcome
        ada logs ./my-project --tail                  # Follow current session
        ada logs ./my-project --export logs.jsonl    # Export to file
    """
    from datetime import datetime as dt

    path = Path(project_path)
    workspace = WorkspaceManager(path)

    if not workspace.exists():
        console.print("[yellow]No .ada/ workspace found. Run 'ada init' or 'ada migrate' first.[/yellow]")
        return

    # Handle export
    if export_file:
        export_path = Path(export_file)
        session_ids = [session_id] if session_id else None
        count = export_sessions_to_jsonl(
            workspace.sessions_dir,
            export_path,
            session_ids=session_ids
        )
        console.print(f"[green]OK[/green] Exported {count} entries to {export_path}")
        return

    # Handle tail mode
    if tail:
        current_id = workspace.get_current_session_id()
        if not current_id:
            console.print("[yellow]No active session to follow.[/yellow]")
            return

        log_path = workspace.get_session_log_path(current_id)
        console.print(f"[dim]Following session: {current_id}[/dim]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        try:
            if output_format == "json":
                import json
                from .session_logger import stream_session_log
                for entry in stream_session_log(log_path, follow=True):
                    print(json.dumps(entry, default=str))
            else:
                for line in stream_session_pretty(log_path, follow=True):
                    console.print(line)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped following.[/dim]")
        return

    # Handle specific session view
    if session_id:
        log_path = workspace.get_session_log_path(session_id)
        if not log_path.exists():
            console.print(f"[red]Session not found: {session_id}[/red]")
            return

        if output_format == "json":
            from .session_logger import read_session_log
            import json
            entries = read_session_log(log_path)
            for entry in entries:
                print(json.dumps(entry, default=str))
        else:
            renderables = format_session_detail(log_path)
            for r in renderables:
                console.print(r)
        return

    # List sessions with filters
    index = workspace.get_session_index()
    sessions = index.sessions.copy()

    # Apply filters
    if feature_id:
        sessions = [s for s in sessions if s.feature_id == feature_id]

    if outcome:
        sessions = [s for s in sessions if s.outcome == outcome]

    if since:
        try:
            since_date = dt.strptime(since, "%Y-%m-%d")
            sessions = [s for s in sessions if s.started_at >= since_date]
        except ValueError:
            console.print(f"[red]Invalid date format: {since}. Use YYYY-MM-DD.[/red]")
            return

    if errors:
        # Only sessions that have errors (need to scan log files)
        from .session_logger import get_session_summary
        filtered = []
        for s in sessions:
            log_path = workspace.get_session_log_path(s.session_id)
            summary = get_session_summary(log_path)
            if summary and summary.get("errors"):
                filtered.append(s)
        sessions = filtered

    # Sort by date (newest first) and limit
    sessions = sorted(sessions, key=lambda s: s.started_at, reverse=True)[:limit]

    if not sessions:
        console.print("[yellow]No sessions found matching filters.[/yellow]")
        return

    # Display
    if output_format == "json":
        import json
        for s in sessions:
            print(json.dumps(s.model_dump(mode="json"), default=str))
    else:
        table = format_session_list(sessions)
        console.print(table)
        console.print(f"\n[dim]Showing {len(sessions)} session(s)[/dim]")


@main.command()
@click.argument('project_path', type=click.Path(exists=True))
@click.option('--fix', is_flag=True, help='Auto-fix safe issues')
@click.option('--fix-all', is_flag=True, help='Fix all issues with prompts')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def health(project_path: str, fix: bool, fix_all: bool, output_json: bool):
    """Check workspace health and optionally fix issues.

    Performs comprehensive health checks on the .ada/ workspace including:
    - Crashed sessions (session_start without session_end)
    - Stale current session pointers
    - Orphan log files
    - Missing log files referenced by index
    - Session ID collisions
    - Uncommitted git changes
    - Features stuck in in_progress

    \b
    Examples:
        ada health ./my-project                  # Check health
        ada health ./my-project --fix            # Auto-fix safe issues
        ada health ./my-project --fix-all        # Fix all issues with prompts
        ada health ./my-project --json           # Output as JSON
    """
    from .workspace_health import WorkspaceHealthChecker, WorkspaceCleaner
    from .models import HealthIssueSeverity

    path = Path(project_path)
    workspace = WorkspaceManager(path)

    if not workspace.exists():
        console.print("[yellow]No .ada/ workspace found. Run 'ada init' first.[/yellow]")
        return

    # Run health checks
    checker = WorkspaceHealthChecker(path, workspace=workspace)
    report = checker.check_all()

    # Auto-fix if requested
    if fix or fix_all:
        cleaner = WorkspaceCleaner(path, workspace=workspace)
        fixed = cleaner.fix_auto(report)
        if fixed:
            console.print(f"[green]Auto-fixed {len(fixed)} issue(s)[/green]")

    # Handle non-auto-fixable issues with prompts (--fix-all)
    if fix_all:
        for issue in report.issues:
            if not issue.auto_fixable:
                console.print(f"\n[yellow]Cannot auto-fix:[/yellow] {issue.message}")
                if issue.fix_description:
                    console.print(f"  [dim]{issue.fix_description}[/dim]")

    # Output results
    if output_json:
        import json
        print(json.dumps(report.model_dump(mode="json"), default=str, indent=2))
        return

    # Console output
    if report.healthy:
        console.print(f"\n[green]{SYM_OK} Workspace is healthy[/green]")
        if report.issues_fixed:
            console.print(f"  [dim]({len(report.issues_fixed)} issue(s) were fixed)[/dim]")
        return

    console.print(f"\n[bold]Workspace Health Report[/bold]")
    console.print(f"Project: {path}")
    console.print(f"Checked: {report.checked_at.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print()

    # Summary
    console.print(f"[red]Critical:[/red] {report.critical_count}  "
                  f"[yellow]Warning:[/yellow] {report.warning_count}  "
                  f"[dim]Info:[/dim] {report.info_count}")

    if report.issues_fixed:
        console.print(f"[green]Fixed:[/green] {len(report.issues_fixed)}")

    # Show issues
    console.print("\n[bold]Issues:[/bold]")

    severity_colors = {
        HealthIssueSeverity.CRITICAL: "red",
        HealthIssueSeverity.WARNING: "yellow",
        HealthIssueSeverity.INFO: "dim",
    }

    for issue in report.issues:
        color = severity_colors.get(issue.severity, "white")
        fix_marker = "[auto]" if issue.auto_fixable else ""
        console.print(f"  [{color}]{issue.severity.value.upper()}[/{color}] {issue.message} {fix_marker}")
        if issue.details:
            console.print(f"    [dim]{issue.details}[/dim]")
        if issue.fix_description and not fix and not fix_all:
            console.print(f"    [dim]Fix: {issue.fix_description}[/dim]")

    # Show fixed issues if any
    if report.issues_fixed:
        console.print("\n[bold]Fixed:[/bold]")
        for issue in report.issues_fixed:
            console.print(f"  [green]{SYM_OK}[/green] {issue.message}")

    # Hint for fixing
    if not fix and not fix_all:
        auto_fixable = sum(1 for i in report.issues if i.auto_fixable)
        if auto_fixable > 0:
            console.print(f"\n[dim]Run with --fix to auto-fix {auto_fixable} issue(s)[/dim]")

    # Error exit code if critical issues
    if report.critical_count > 0:
        console.print(f"\n[red]{SYM_FAIL} Critical issues found - run 'ada health --fix-all' to attempt repair[/red]")
        raise SystemExit(1)


if __name__ == '__main__':
    main()

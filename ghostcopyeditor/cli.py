"""GhostCopyeditor CLI — copy editor for fiction manuscripts."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from ghostcopyeditor.config import GhostCopyeditorConfig

__all__ = ["app"]

app = typer.Typer(
    name="ghostcopyeditor",
    help=(
        "Copy editor for Ghost writing suite manuscripts.\n\n"
        "Checks grammar, garbled text, style, and light wordiness/echo.\n\n"
        "Quick start:\n\n"
        "  ghostcopyeditor init              Create config.yaml + .ghostcopyeditor/\n"
        "  ghostcopyeditor companion ./chapters/chapter-018.md\n"
        "  ghostcopyeditor analyze ./chapters\n"
    ),
    no_args_is_help=True,
)

config_app = typer.Typer(help="View or edit configuration.")
app.add_typer(config_app, name="config")

FormatOption = Annotated[
    Optional[str],
    typer.Option("--format", help="Output format: terminal (default) or json."),
]
OutputOption = Annotated[
    Optional[Path],
    typer.Option("--output", "-o", help="Write an additional copy of the report JSON."),
]
TypesafeOption = Annotated[
    Optional[bool],
    typer.Option(
        "--typesafe/--no-typesafe",
        help="Use TypeSafe for judgments (overrides config.yaml). Default: config or off.",
    ),
]
ModelOption = Annotated[
    Optional[str],
    typer.Option("--model", help="LLM model override. Takes precedence over config.yaml."),
]
ApplyOption = Annotated[
    bool,
    typer.Option("--apply/--no-apply", help="Apply safe deterministic fixes only."),
]
NoLlmOption = Annotated[
    bool,
    typer.Option("--no-llm", help="Skip the LLM engine."),
]
VerboseOption = Annotated[
    bool,
    typer.Option("--verbose", help="More progress on stderr."),
]


@app.command()
def init(
    directory: Annotated[
        Path, typer.Argument(help="Directory in which to create config.yaml.")
    ] = Path("."),
) -> None:
    """Create config.yaml and an empty .ghostcopyeditor/ state directory."""
    directory = directory.resolve()
    cfg_path = directory / "config.yaml"

    if cfg_path.exists():
        rprint(f"[yellow]config.yaml already exists at:[/yellow] {cfg_path}")
        raise typer.Exit(code=1)

    directory.mkdir(parents=True, exist_ok=True)
    cfg = GhostCopyeditorConfig()
    written = cfg.save(directory)
    state_dir = directory / ".ghostcopyeditor"
    state_dir.mkdir(parents=True, exist_ok=True)

    rprint(
        Panel(
            f"[green]Config created:[/green] {written}\n"
            f"[green]State dir:[/green] {state_dir}\n"
            "  Defaults keep TypeSafe and LLM off until you add keys.\n"
            "  1. Copy secrets/llm.example → secrets/llm.env and fill keys.\n"
            "  2. Then: ghostcopyeditor config set typesafe_enabled true\n"
            "     and/or: ghostcopyeditor config set llm_enabled true\n"
            "     (or pass --typesafe / --model on the command).",
            title="ghostcopyeditor init",
        )
    )


@app.command()
def companion(
    path: Annotated[
        Path,
        typer.Argument(help="chapter-NNN.md for a single-chapter copy-edit check."),
    ],
    format: FormatOption = None,
    output: OutputOption = None,
    typesafe: TypesafeOption = None,
    model: ModelOption = None,
    apply: ApplyOption = False,
    no_llm: NoLlmOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Copy-edit one chapter (Autonomicon hook). Engines land in later PRs."""
    from ghostcopyeditor.commands.companion import run_companion

    path = path.resolve()
    cfg = GhostCopyeditorConfig.load(path)
    output_format = format or cfg.format or "terminal"
    run_companion(
        path,
        output_format=output_format,
        output_path=output,
        typesafe=typesafe,
        no_llm=no_llm,
        apply=apply,
        model=model,
        verbose=verbose,
    )


@app.command()
def analyze(
    path: Annotated[
        Path,
        typer.Argument(help="Chapter folder or story dir with chapters/."),
    ],
    format: FormatOption = None,
    output: OutputOption = None,
    typesafe: TypesafeOption = None,
    model: ModelOption = None,
    apply: ApplyOption = False,
    no_llm: NoLlmOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Copy-edit a chapter folder (combined report). Engines land in later PRs."""
    from ghostcopyeditor.commands.analyze import run_analyze

    path = path.resolve()
    cfg = GhostCopyeditorConfig.load(path)
    output_format = format or cfg.format or "terminal"
    run_analyze(
        path,
        output_format=output_format,
        output_path=output,
        typesafe=typesafe,
        no_llm=no_llm,
        apply=apply,
        model=model,
        verbose=verbose,
    )


@config_app.callback(invoke_without_command=True)
def config_show(
    ctx: typer.Context,
) -> None:
    """View current configuration."""
    if ctx.invoked_subcommand is not None:
        return

    from ghostcopyeditor.paths import config_path as _find_cfg

    cfg_file = _find_cfg()
    cfg = GhostCopyeditorConfig.load()
    label = str(cfg_file) if cfg_file else "(defaults — no config.yaml found)"

    table = Table(title=f"Config — {label}")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")

    for key, value in cfg.model_dump().items():
        display = str(value) if value is not None else "[dim](not set)[/dim]"
        table.add_row(key, display)

    rprint(table)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key to set.")],
    value: Annotated[str, typer.Argument(help="New value.")],
) -> None:
    """Set a configuration value in config.yaml."""
    from ghostcopyeditor.paths import find_project_root

    root = find_project_root()
    if root is None:
        rprint(
            "[red]Error:[/red] No config.yaml found. "
            "Run [cyan]ghostcopyeditor init[/cyan] first."
        )
        raise typer.Exit(code=1)

    cfg = GhostCopyeditorConfig.load()
    data = cfg.model_dump()

    if key not in data:
        rprint(f"[red]Error:[/red] Unknown config key '{key}'.")
        rprint(f"Valid keys: {', '.join(data.keys())}")
        raise typer.Exit(code=1)

    current = data[key]
    if isinstance(current, bool):
        coerced: object = value.lower() in ("true", "1", "yes")
    elif isinstance(current, float) or key in (
        "temperature",
        "typesafe_confidence_floor",
        "typesafe_noul_positive_threshold",
    ):
        coerced = float(value)
    elif isinstance(current, int) or key in (
        "max_tokens",
        "echo_window_words",
        "echo_min_repeats",
    ):
        if value.lower() in ("null", "none", ""):
            coerced = None
        else:
            coerced = int(value)
    elif current is None and value.lower() in ("null", "none", ""):
        coerced = None
    else:
        coerced = value

    data[key] = coerced
    updated = GhostCopyeditorConfig(**data)
    updated.save(root)

    rprint(f"[green]Set[/green] {key} = {coerced}")

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from . import __version__, graphify_bridge
from . import pipeline as pipeline_module
from . import update as update_module
from .config import CortexConfig, config_file_path, resolve_config, write_starter_config
from .providers import MissingAPIKeyError, get_triage_provider
from .triage import pipeline as triage_pipeline

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Trie un dossier de fichiers, en fait un vault Obsidian curé par un LLM, puis "
    "construit un graphe de connaissances interrogeable avec Graphify.",
)
config_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Gestion de la configuration.")
app.add_typer(config_app, name="config")

console = Console()

ProviderOpt = typer.Option(None, "--provider", help="anthropic (defaut), claude-cli (abonnement Claude Code local) ou openai-compatible.")
ModelOpt = typer.Option(None, "--model", help="Modele pour le triage ET la generation du vault.")
TriageModelOpt = typer.Option(None, "--triage-model", help="Modele utilise pour le triage (defaut : economique).")
VaultModelOpt = typer.Option(None, "--vault-model", help="Modele utilise pour la generation du vault (defaut : qualite).")
BaseUrlOpt = typer.Option(None, "--base-url", help="URL de l'endpoint compatible OpenAI (Ollama local ou cloud).")
BatchSizeOpt = typer.Option(None, "--batch-size", help="Taille des lots pour les appels LLM du triage.")


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"cortex {__version__}")
        raise typer.Exit()


def _maybe_auto_update() -> None:
    """Verifie (avec cache 24h) si un nouveau commit existe sur main, et le signale.
    N'applique jamais la mise a jour automatiquement : `apply_update` reinstalle le
    venv courant via `uv tool install --force` / equivalent, ce qui remplace les
    fichiers (dont l'interpreteur) du processus cortex en train de tourner. Sur
    Windows ce remplacement echoue systematiquement ("Access is denied", fichier
    verrouille par le processus courant) et peut laisser l'installation dans un etat
    casse (ex: Lib/site-packages supprime avant l'echec). On se contente donc de
    notifier ; la mise a jour reelle se fait via `cortex update`, execute hors de
    tout processus cortex en cours."""
    latest = update_module.check_for_update()
    if not latest:
        return
    console.print(
        f"[yellow]Mise à jour cortex disponible ({latest[:7]}). "
        "Lance `cortex update` pour l'appliquer.[/yellow]"
    )


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True, help="Affiche la version et quitte."
    ),
) -> None:
    if ctx.invoked_subcommand != "update":
        _maybe_auto_update()


def _build_config(
    provider: Optional[str],
    model: Optional[str],
    triage_model: Optional[str],
    vault_model: Optional[str],
    base_url: Optional[str],
    batch_size: Optional[int],
) -> CortexConfig:
    try:
        return resolve_config(
            provider=provider,
            model=model,
            triage_model=triage_model,
            vault_model=vault_model,
            base_url=base_url,
            batch_size=batch_size,
        )
    except ValueError as exc:
        console.print(f"[red]Erreur de configuration :[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _note_progress_reporter(console: Console):
    """Barre de progression pour la generation du vault : nombre de notes generees /
    total, et nombre de fichiers ecartes au triage (non pertinents pour un LLM -- p.ex.
    un CSV de valeurs numeriques). La barre demarre au premier appel (des qu'on connait
    le total) et s'arrete d'elle-meme a la fin ; `stop()` permet de la couper proprement
    si le pipeline leve une exception en cours de route."""
    holder: dict = {"progress": None, "task_id": None}

    def on_note_progress(done: int, total: int, dropped: int) -> None:
        progress = holder["progress"]
        if progress is None:
            progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total} notes"),
                TextColumn("· {task.fields[dropped]} fichiers écartés (non pertinents)"),
                TimeElapsedColumn(),
                console=console,
            )
            progress.start()
            holder["progress"] = progress
            holder["task_id"] = progress.add_task("Génération du vault", total=total, dropped=dropped)
        progress.update(holder["task_id"], completed=done, dropped=dropped)
        if done >= total:
            progress.stop()

    def stop() -> None:
        if holder["progress"] is not None:
            holder["progress"].stop()

    return on_note_progress, stop


@app.command()
def build(
    path: Path = typer.Argument(..., exists=True, file_okay=False, help="Dossier source a traiter."),
    output: Path = typer.Option(Path("cortex-out"), "--output", help="Dossier de sortie."),
    provider: Optional[str] = ProviderOpt,
    model: Optional[str] = ModelOpt,
    triage_model: Optional[str] = TriageModelOpt,
    vault_model: Optional[str] = VaultModelOpt,
    base_url: Optional[str] = BaseUrlOpt,
    batch_size: Optional[int] = BatchSizeOpt,
    dry_run: bool = typer.Option(False, "--dry-run", help="Triage seul, n'ecrit ni vault ni graphe."),
    skip_graphify: bool = typer.Option(False, "--skip-graphify", help="Genere le vault mais ne lance pas graphify."),
) -> None:
    """Pipeline complet : triage -> vault -> graphify."""
    config = _build_config(provider, model, triage_model, vault_model, base_url, batch_size)
    on_note_progress, stop_progress = _note_progress_reporter(console)
    try:
        result = pipeline_module.build(
            path,
            output,
            config,
            dry_run=dry_run,
            skip_graphify=skip_graphify,
            on_progress=console.print,
            on_note_progress=on_note_progress,
        )
    except (ValueError, graphify_bridge.GraphifyError) as exc:
        stop_progress()
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if dry_run:
        for d in result.triage_decisions:
            style = "green" if d.decision == "keep" else "yellow"
            console.print(f"[{style}]{d.decision:5}[/{style}] {d.path}  ({d.source}) {d.reason}")
        return

    console.print(f"[bold green]Vault genere :[/bold green] {result.vault_dir} ({len(result.notes)} notes)")
    if result.graphify_ran:
        console.print(f"[bold green]Graphe construit :[/bold green] {result.vault_dir / 'graphify-out'}")


@app.command()
def triage(
    path: Path = typer.Argument(..., exists=True, file_okay=False, help="Dossier source a trier."),
    provider: Optional[str] = ProviderOpt,
    model: Optional[str] = ModelOpt,
    triage_model: Optional[str] = TriageModelOpt,
    vault_model: Optional[str] = VaultModelOpt,
    base_url: Optional[str] = BaseUrlOpt,
    batch_size: Optional[int] = BatchSizeOpt,
    as_json: bool = typer.Option(False, "--json", help="Sortie JSON plutot qu'un rapport lisible."),
) -> None:
    """Etape de tri seule : garder/ecarter chaque fichier, avec la raison."""
    config = _build_config(provider, model, triage_model, vault_model, base_url, batch_size)
    try:
        llm_provider = get_triage_provider(config)
    except MissingAPIKeyError:
        llm_provider = None
        console.print("No LLM provider configured (missing API key) -- ambiguous files will be kept by default.")
    decisions = triage_pipeline.run(path, llm_provider, batch_size=config.batch_size)

    if as_json:
        console.print_json(json.dumps([d.to_dict() for d in decisions], ensure_ascii=False))
        return

    kept = sum(1 for d in decisions if d.decision == "keep")
    for d in decisions:
        style = "green" if d.decision == "keep" else "yellow"
        console.print(f"[{style}]{d.decision:5}[/{style}] {d.path}  ({d.source}) {d.reason}")
    console.print(f"\n{len(decisions)} fichiers -> {kept} conserves, {len(decisions) - kept} ecartes")


@app.command()
def vault(
    path: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="Dossier source (le triage est relance si necessaire)."
    ),
    output: Path = typer.Option(Path("cortex-out"), "--output", help="Dossier de sortie."),
    provider: Optional[str] = ProviderOpt,
    model: Optional[str] = ModelOpt,
    triage_model: Optional[str] = TriageModelOpt,
    vault_model: Optional[str] = VaultModelOpt,
    base_url: Optional[str] = BaseUrlOpt,
    batch_size: Optional[int] = BatchSizeOpt,
) -> None:
    """Etape de generation du vault seule (triage + notes + liens, sans graphify)."""
    config = _build_config(provider, model, triage_model, vault_model, base_url, batch_size)
    on_note_progress, stop_progress = _note_progress_reporter(console)
    try:
        result = pipeline_module.build(
            path,
            output,
            config,
            dry_run=False,
            skip_graphify=True,
            on_progress=console.print,
            on_note_progress=on_note_progress,
        )
    except ValueError as exc:
        stop_progress()
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[bold green]Vault genere :[/bold green] {result.vault_dir} ({len(result.notes)} notes)")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def graph(
    ctx: typer.Context,
    vault_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="Dossier du vault a passer a graphify."),
) -> None:
    """Lance `graphify <vault-dir>` (passthrough). Toute option non reconnue est transmise a graphify."""
    notice = graphify_bridge.semantic_extraction_notice()
    if notice:
        console.print(notice)
    try:
        result = graphify_bridge.run_graphify(vault_dir, list(ctx.args))
    except graphify_bridge.GraphifyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(result.stdout)


@app.command()
def query(
    question: str = typer.Argument(..., help="Question a poser au graphe."),
    graph_dir: Path = typer.Option(
        Path("cortex-out/vault"), "--graph-dir", help="Dossier contenant graphify-out/ (le vault genere)."
    ),
) -> None:
    """Passthrough vers `graphify query "<question>"`."""
    try:
        output = graphify_bridge.run_graphify_query(question, graph_dir)
    except graphify_bridge.GraphifyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(output)


@app.command()
def update() -> None:
    """Verifie et applique une mise a jour de cortex depuis GitHub (branche main).

    Cortex n'est pas publie sur PyPI : chaque nouveau commit sur main est la version
    la plus recente. Cette commande force la verification (ignore le cache de 24h)
    et applique la mise a jour selon la methode d'installation detectee (uv tool,
    pipx, pip --user, ou `git pull` pour une install editable de dev)."""
    installed = update_module.get_installed_info()
    if installed.commit is None:
        console.print(
            "[yellow]Impossible de determiner la version installee "
            "(metadonnees d'installation absentes ou non standard).[/yellow]"
        )
        raise typer.Exit(code=1)

    latest = update_module.check_for_update(force=True)
    if not latest:
        console.print(f"[green]Deja a jour[/green] ({installed.commit[:7]}).")
        return

    console.print(f"[yellow]Nouvelle version disponible ({latest[:7]}), mise a jour...[/yellow]")
    ok, message = update_module.apply_update(installed)
    style = "green" if ok else "red"
    console.print(f"[{style}]{message}[/{style}]")
    if not ok:
        raise typer.Exit(code=1)


@config_app.command("show")
def config_show(
    provider: Optional[str] = ProviderOpt,
    model: Optional[str] = ModelOpt,
    triage_model: Optional[str] = TriageModelOpt,
    vault_model: Optional[str] = VaultModelOpt,
    base_url: Optional[str] = BaseUrlOpt,
    batch_size: Optional[int] = BatchSizeOpt,
) -> None:
    """Affiche la configuration resolue (jamais la cle API en clair)."""
    config = _build_config(provider, model, triage_model, vault_model, base_url, batch_size)
    console.print(f"provider      = {config.provider}")
    console.print(f"api_key       = {'definie' if config.has_api_key() else 'absente'}")
    console.print(f"base_url      = {config.base_url or '(non definie)'}")
    console.print(f"triage_model  = {config.triage_model or '(non definie)'}")
    console.print(f"vault_model   = {config.vault_model or '(non definie)'}")
    console.print(f"batch_size    = {config.batch_size}")
    console.print(f"config file   = {config_file_path()}")


@config_app.command("init")
def config_init() -> None:
    """Ecrit un config.toml de depart (commente) dans le repertoire de config standard."""
    path = write_starter_config()
    console.print(f"[bold green]Config ecrite :[/bold green] {path}")


if __name__ == "__main__":
    app()

"""Session interactive lancee par `cortex` sans sous-commande, a la maniere de `claude`.

Reste dans la session pour taper directement des commandes existantes (`build`,
`triage`, `vault`, `graph`, `query`, `update`) ou des commandes slash (`/provider`,
`/model`, `/effort`, `/exclude`, `/config`, `/help`, `/clear`, `/exit`) qui modifient
la configuration de la session courante sans jamais toucher a `config.toml`.
"""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass, field
from typing import Literal

import questionary
from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

from . import __version__
from .config import VALID_EFFORT_LEVELS, CortexConfig, resolve_config

_VIOLET = "#8b5cf6"

_PROVIDERS = ("anthropic", "claude-cli", "openai-compatible")


def _split_line(line: str) -> list[str]:
    """Comme shlex.split, mais sans traiter `\\` comme un caractere d'echappement --
    shlex.split standard (mode posix) mange les antislashs des chemins Windows tapes
    tels quels (ex. `build C:\\notes` devient `C:notes`). En mode non-posix, shlex
    garde les guillemets autour des tokens cites ; on les retire nous-memes ensuite."""
    tokens = shlex.split(line, posix=False)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in tokens]

# Glyphs are plain ASCII on purpose (no box-drawing/block Unicode characters): the
# default console codepage on many Windows setups (cp1252, cp437, ...) cannot encode
# U+2580-259F block characters, and rich's legacy-console renderer crashes with a
# raw UnicodeEncodeError instead of degrading gracefully -- confirmed by hand against
# both a git-bash and a native PowerShell console on this machine. Plain ASCII is
# encodable in every codepage, so the banner is safe everywhere.
_HEX_C = [
    "   _____   ",
    "  /     \\  ",
    " /       | ",
    "|          ",
    "|          ",
    "|          ",
    " \\       | ",
    "  \\_____/  ",
    "           ",
]

_BLOCK_O = [
    " ####### ",
    "##     ##",
    "##     ##",
    "##     ##",
    "##     ##",
    "##     ##",
    "##     ##",
    "##     ##",
    " ####### ",
]

_BLOCK_R = [
    "######## ",
    "##     ##",
    "##     ##",
    "##     ##",
    "######## ",
    "##   ##  ",
    "##    ## ",
    "##     ##",
    "##     ##",
]

_BLOCK_T = [
    "#########",
    "   ###   ",
    "   ###   ",
    "   ###   ",
    "   ###   ",
    "   ###   ",
    "   ###   ",
    "   ###   ",
    "   ###   ",
]

_BLOCK_E = [
    "######## ",
    "##       ",
    "##       ",
    "##       ",
    "#######  ",
    "##       ",
    "##       ",
    "##       ",
    "######## ",
]

_BLOCK_X = [
    "##     ##",
    " ##   ## ",
    "  ## ##  ",
    "   ###   ",
    "   ###   ",
    "   ###   ",
    "  ## ##  ",
    " ##   ## ",
    "##     ##",
]


def render_banner() -> Group:
    lines: list[Text] = []
    for i in range(9):
        line = Text()
        line.append(_HEX_C[i], style=f"bold {_VIOLET}")
        line.append("  ")
        line.append(_BLOCK_O[i] + _BLOCK_R[i] + _BLOCK_T[i] + _BLOCK_E[i], style="bold white")
        line.append(" ")
        line.append(_BLOCK_X[i], style=f"bold {_VIOLET}")
        lines.append(line)
    subtitle = Text(f"  v{__version__}  -  session interactive  -  tape /help pour la liste des commandes", style="dim")
    return Group(*lines, Text(""), subtitle)


def format_status_line(config: CortexConfig) -> Text:
    text = Text()
    text.append("provider ", style="dim")
    text.append(config.provider, style="bold")
    text.append("  |  triage ", style="dim")
    text.append(config.triage_model or "(non defini)", style="bold")
    text.append("  |  vault ", style="dim")
    text.append(config.vault_model or "(non defini)", style="bold")
    text.append("  |  effort ", style="dim")
    effort = config.triage_effort or config.vault_effort or "(defaut API)"
    text.append(effort, style="bold")
    return text


@dataclass
class SessionState:
    config: CortexConfig
    exclude: list[str] = field(default_factory=list)


def _interactive_available() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def pick_provider(current: str) -> str | None:
    if not _interactive_available():
        return None
    try:
        return questionary.select(
            "Choisis le provider LLM :",
            choices=list(_PROVIDERS),
            default=current if current in _PROVIDERS else None,
        ).ask()
    except Exception:
        return None


def pick_model(kind: Literal["triage", "vault", "both"], current: str | None) -> str | None:
    label = {"both": "le triage ET le vault", "triage": "le triage", "vault": "le vault"}[kind]
    if not _interactive_available():
        return None
    try:
        result = questionary.text(f"Modele pour {label} (actuel : {current or 'non defini'}) :").ask()
    except Exception:
        return None
    return result or None


def pick_effort(current: str | None, provider: str) -> str | None:
    if not _interactive_available():
        return None
    note = "" if provider == "anthropic" else "  (ignore par ce provider)"
    try:
        return questionary.select(
            f"Niveau d'effort de raisonnement{note} :",
            choices=list(VALID_EFFORT_LEVELS),
            default=current if current in VALID_EFFORT_LEVELS else None,
        ).ask()
    except Exception:
        return None


def _session_flags(config: CortexConfig) -> list[str]:
    flags: list[str] = ["--provider", config.provider]
    if config.triage_model:
        flags += ["--triage-model", config.triage_model]
    if config.vault_model:
        flags += ["--vault-model", config.vault_model]
    if config.triage_effort:
        flags += ["--triage-effort", config.triage_effort]
    if config.vault_effort:
        flags += ["--vault-effort", config.vault_effort]
    if config.base_url:
        flags += ["--base-url", config.base_url]
    flags += ["--batch-size", str(config.batch_size)]
    return flags


def _invoke(argv: list[str], console: Console) -> None:
    from .cli import app

    try:
        app(args=argv, standalone_mode=False, prog_name="cortex")
    except SystemExit:
        pass
    except Exception as exc:
        console.print(f"[red]Erreur :[/red] {exc}")


def _resolve_from_session(session: SessionState, **overrides: object) -> CortexConfig:
    base: dict[str, object] = dict(
        provider=session.config.provider,
        base_url=session.config.base_url,
        triage_model=session.config.triage_model,
        vault_model=session.config.vault_model,
        triage_effort=session.config.triage_effort,
        vault_effort=session.config.vault_effort,
        batch_size=session.config.batch_size,
    )
    base.update(overrides)
    return resolve_config(**base)  # type: ignore[arg-type]


def _print_help(console: Console) -> None:
    table = Table(title="Commandes disponibles", show_header=True, header_style="bold")
    table.add_column("Commande")
    table.add_column("Description")
    for cmd, desc in [
        ("build <dossier> [options]", "Pipeline complet : triage -> vault -> graphify."),
        ("triage <dossier> [options]", "Etape de tri seule."),
        ("vault <dossier> [options]", "Genere le vault sans lancer graphify."),
        ("graph <vault-dir> [options]", "Passthrough vers graphify."),
        ('query "<question>"', "Passthrough vers graphify query."),
        ("update", "Verifie et applique une mise a jour de cortex."),
        ("/provider [nom]", "Change le provider LLM de la session (menu si aucun nom)."),
        ("/model [triage|vault|both] [nom]", "Change le(s) modele(s) de la session."),
        ("/effort [triage|vault|both] [niveau]", "Change le niveau d'effort de la session."),
        ("/exclude add|remove|list|clear [motifs]", "Gere les motifs d'exclusion par defaut de la session."),
        ("/config", "Affiche la configuration resolue de la session."),
        ("/clear", "Efface l'ecran et reaffiche la banniere."),
        ("/exit, /quit", "Quitte la session."),
    ]:
        table.add_row(cmd, desc)
    console.print(table)


def _dispatch_model_or_effort_target(args: list[str]) -> tuple[str, str | None]:
    if len(args) >= 2:
        return args[0], args[1]
    if len(args) == 1:
        if args[0] in ("triage", "vault", "both"):
            return args[0], None
        return "both", args[0]
    return "both", None


def _dispatch_slash(line: str, session: SessionState, console: Console) -> None:
    from .cli import _print_config

    parts = _split_line(line)
    cmd = parts[0][1:]
    args = parts[1:]

    if cmd == "provider":
        new_provider = args[0] if args else pick_provider(session.config.provider)
        if not new_provider:
            console.print("[yellow]Annule.[/yellow]")
            return
        if new_provider not in _PROVIDERS:
            console.print(f"[red]Provider inconnu :[/red] {new_provider!r}. Valeurs acceptees : {', '.join(_PROVIDERS)}.")
            return
        try:
            session.config = resolve_config(provider=new_provider)
        except ValueError as exc:
            console.print(f"[red]Erreur de configuration :[/red] {exc}")
            return
        console.print(f"[green]Provider :[/green] {session.config.provider}")
        console.print(
            "[dim]Modele/effort reinitialises a leurs valeurs par defaut ; "
            "/model et /effort pour les redefinir.[/dim]"
        )

    elif cmd == "model":
        target, name = _dispatch_model_or_effort_target(args)
        if target not in ("triage", "vault", "both"):
            console.print(f"[red]Cible inconnue :[/red] {target!r}. Utilise triage, vault ou both.")
            return
        if name is None:
            current = session.config.vault_model if target == "vault" else session.config.triage_model
            name = pick_model(target, current)
        if not name:
            console.print("[yellow]Annule.[/yellow]")
            return
        overrides: dict[str, object] = {}
        if target in ("triage", "both"):
            overrides["triage_model"] = name
        if target in ("vault", "both"):
            overrides["vault_model"] = name
        try:
            session.config = _resolve_from_session(session, **overrides)
        except ValueError as exc:
            console.print(f"[red]Erreur de configuration :[/red] {exc}")
            return
        console.print(f"[green]Modele mis a jour[/green] ({target}) : {name}")

    elif cmd == "effort":
        target, level = _dispatch_model_or_effort_target(args)
        if target not in ("triage", "vault", "both"):
            console.print(f"[red]Cible inconnue :[/red] {target!r}. Utilise triage, vault ou both.")
            return
        if level is None:
            current = session.config.vault_effort if target == "vault" else session.config.triage_effort
            level = pick_effort(current, session.config.provider)
        if not level:
            console.print("[yellow]Annule.[/yellow]")
            return
        if level not in VALID_EFFORT_LEVELS:
            console.print(f"[red]Niveau d'effort invalide :[/red] {level!r}. Valeurs acceptees : {', '.join(VALID_EFFORT_LEVELS)}.")
            return
        overrides = {}
        if target in ("triage", "both"):
            overrides["triage_effort"] = level
        if target in ("vault", "both"):
            overrides["vault_effort"] = level
        try:
            session.config = _resolve_from_session(session, **overrides)
        except ValueError as exc:
            console.print(f"[red]Erreur de configuration :[/red] {exc}")
            return
        console.print(f"[green]Effort mis a jour[/green] ({target}) : {level}")
        if session.config.provider != "anthropic":
            console.print(f"[dim]Note : ignore par le provider courant ({session.config.provider}).[/dim]")

    elif cmd == "exclude":
        if not args:
            console.print(f"Exclusions : {session.exclude or '(aucune)'}")
            return
        sub, rest = args[0], args[1:]
        if sub == "add":
            session.exclude.extend(rest)
            console.print(f"[green]Ajoute :[/green] {rest}")
        elif sub == "remove":
            for pat in rest:
                if pat in session.exclude:
                    session.exclude.remove(pat)
            console.print(f"Exclusions : {session.exclude or '(aucune)'}")
        elif sub == "list":
            console.print(f"Exclusions : {session.exclude or '(aucune)'}")
        elif sub == "clear":
            session.exclude.clear()
            console.print("[green]Exclusions videes.[/green]")
        else:
            console.print(f"[yellow]Sous-commande inconnue :[/yellow] {sub!r}. add/remove/list/clear.")

    elif cmd == "config":
        _print_config(console, session.config)

    elif cmd == "help":
        _print_help(console)

    elif cmd == "clear":
        console.clear()
        console.print(render_banner())
        console.print(format_status_line(session.config))

    else:
        console.print(f"[yellow]Commande inconnue :[/yellow] {line!r}. Tape /help.")


def dispatch_line(line: str, session: SessionState, console: Console) -> None:
    from .cli import _expand_exclude_argv

    tokens = _split_line(line)
    if not tokens:
        return
    cmd, rest = tokens[0], tokens[1:]

    if cmd in {"build", "triage", "vault"}:
        exclude_flags = [f for pat in session.exclude for f in ("--exclude", pat)]
        argv = [cmd, *_session_flags(session.config), *exclude_flags, *rest]
        _invoke(_expand_exclude_argv(argv), console)
    elif cmd in {"graph", "query", "update"}:
        _invoke([cmd, *rest], console)
    elif cmd == "config":
        _dispatch_slash("/config", session, console)
    elif cmd == "help":
        _dispatch_slash("/help", session, console)
    else:
        console.print(f"[yellow]Commande inconnue :[/yellow] {cmd!r}. Tape /help.")


def _read_line(console: Console) -> str:
    return console.input(f"[bold {_VIOLET}]cortex>[/bold {_VIOLET}] ")


def run_repl(initial_config: CortexConfig, *, console: Console | None = None) -> None:
    console = console or Console()
    session = SessionState(config=initial_config)
    console.print(render_banner())
    console.print(format_status_line(session.config))
    # Chaque commande tapee dans la session redispatche vers l'app Typer complete
    # (_invoke), dont le callback verifie une mise a jour disponible. Deja fait une
    # fois avant l'entree dans la session (cf. cortex_main) -- l'y refaire a chaque
    # ligne ne ferait qu'imprimer la meme notice en boucle sans jamais rappeler le
    # reseau (cache 24h), donc on la desactive pour le reste de la session.
    os.environ["CORTEX_SKIP_UPDATE_CHECK"] = "1"
    while True:
        try:
            line = _read_line(console).lstrip("﻿").strip()
        except KeyboardInterrupt:
            console.print()
            continue
        except EOFError:
            console.print()
            break
        if not line:
            continue
        if line in ("/exit", "/quit", "exit", "quit"):
            break
        if line.startswith("/"):
            _dispatch_slash(line, session, console)
        else:
            dispatch_line(line, session, console)

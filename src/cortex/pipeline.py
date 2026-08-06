"""Orchestration globale de `cortex build` : triage -> generation du vault -> graphify."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import graphify_bridge
from .config import CortexConfig
from .providers import MissingAPIKeyError, get_triage_provider, get_vault_provider
from .triage import pipeline as triage_pipeline
from .triage.pipeline import TriageDecision
from .vault.generator import apply_links, generate_draft, propose_links
from .vault.linker import resolve_links
from .vault.notes import Note
from .vault.writer import VaultWriter

MAX_SOURCE_CHARS = 60_000  # garde-fou : ne pas envoyer un fichier demesure au LLM de generation


@dataclass
class BuildResult:
    triage_decisions: list[TriageDecision]
    notes: list[Note]
    vault_dir: Path
    graphify_ran: bool


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS] + "\n...[tronque]...\n"
    return text


def build(
    source: Path,
    output_dir: Path,
    config: CortexConfig,
    *,
    dry_run: bool = False,
    skip_graphify: bool = False,
    on_progress: Callable[[str], None] | None = None,
    on_note_progress: Callable[[int, int, int], None] | None = None,
) -> BuildResult:
    """on_note_progress(notes_traitees, notes_a_traiter, fichiers_ecartes) est appele apres
    chaque note (brouillon) generee et ecrite sur disque, pour permettre un suivi visuel
    (barre de progression CLI, vault Obsidian qui se remplit en direct...)."""

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    try:
        triage_provider = get_triage_provider(config)
    except MissingAPIKeyError:
        triage_provider = None
        report("No LLM provider configured (missing API key) -- ambiguous files will be kept by default.")
    decisions = triage_pipeline.run(source, triage_provider, batch_size=config.batch_size)
    kept = [d for d in decisions if d.decision == "keep"]
    dropped = len(decisions) - len(kept)
    report(f"Triage: {len(decisions)} fichiers -> {len(kept)} conserves, {dropped} ecartes")

    if dry_run:
        return BuildResult(decisions, [], output_dir / "vault", graphify_ran=False)

    vault_provider = get_vault_provider(config)
    vault_dir = output_dir / "vault"
    writer = VaultWriter(vault_dir)
    notes: list[Note] = []
    created = datetime.now(timezone.utc).date().isoformat()
    for i, d in enumerate(kept, start=1):
        try:
            content = _read_text(d.path)
        except OSError:
            if on_note_progress:
                on_note_progress(i, len(kept), dropped)
            continue
        note = generate_draft(vault_provider, d.path, content)
        note.created = created
        notes.append(note)
        # Ecriture immediate (avant les liens) : le vault se remplit note par note sur
        # disque, visible en direct dans Obsidian au lieu d'apparaitre d'un coup a la fin.
        writer.write(note)
        if on_note_progress:
            on_note_progress(i, len(kept), dropped)

    links = propose_links(vault_provider, notes)
    apply_links(notes, links)
    resolve_links(notes)

    for note in notes:
        writer.write(note)  # reecrit chaque note une fois les liens resolus
    report(f"Vault genere : {len(notes)} notes dans {vault_dir}")

    graphify_ran = False
    if not skip_graphify:
        notice = graphify_bridge.semantic_extraction_notice()
        if notice:
            report(notice)
        graphify_bridge.run_graphify(vault_dir)
        graphify_ran = True
        report(f"Graphe construit dans {vault_dir / 'graphify-out'}")

    return BuildResult(decisions, notes, vault_dir, graphify_ran)

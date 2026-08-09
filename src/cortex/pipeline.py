"""Orchestration globale de `cortex build` : triage -> generation du vault -> graphify."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import graphify_bridge
from .cache import ProjectCache, composition_hash, hash_file
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
    exclude: list[str] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_note_progress: Callable[[int, int, int], None] | None = None,
) -> BuildResult:
    """on_note_progress(notes_traitees, notes_a_traiter, fichiers_ecartes) est appele apres
    chaque note (brouillon) generee et ecrite sur disque, pour permettre un suivi visuel
    (barre de progression CLI, vault Obsidian qui se remplit en direct...)."""

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    cache = ProjectCache.load(output_dir)

    # Tout le corps de build() tourne sous ce try/finally : si une etape leve (timeout
    # LLM, limite d'usage claude-cli epuisant ses retries, etc.), le cache.save() du
    # finally persiste quand meme sur disque tout ce qui a ete traite avec succes
    # jusque-la (triage et notes deja generees), pour qu'un `cortex build` relance
    # apres coup reprenne la ou ca s'est arrete au lieu de tout refaire (et de
    # reconsommer le meme quota LLM pour rien).
    try:
        try:
            triage_provider = get_triage_provider(config)
        except MissingAPIKeyError:
            triage_provider = None
            report("No LLM provider configured (missing API key) -- ambiguous files will be kept by default.")
        decisions = triage_pipeline.run(source, triage_provider, batch_size=config.batch_size, cache=cache, exclude=exclude)
        kept = [d for d in decisions if d.decision == "keep"]
        dropped = len(decisions) - len(kept)
        report(f"Triage: {len(decisions)} fichiers -> {len(kept)} conserves, {dropped} ecartes")

        if dry_run:
            return BuildResult(decisions, [], output_dir / "vault", graphify_ran=False)

        vault_provider = get_vault_provider(config)
        vault_dir = output_dir / "vault"
        writer = VaultWriter(vault_dir)
        notes: list[Note] = []
        note_hashes: list[str] = []
        created = datetime.now(timezone.utc).date().isoformat()
        reused = 0
        for i, d in enumerate(kept, start=1):
            try:
                file_hash = hash_file(d.path)
            except OSError:
                if on_note_progress:
                    on_note_progress(i, len(kept), dropped)
                continue

            cached_entry = cache.cached_note(d.path, file_hash)
            if cached_entry is not None:
                # Fichier inchange depuis le dernier build (meme hash) : reutilise la note
                # deja generee, aucun appel LLM.
                note = Note(
                    title=cached_entry["title"],
                    source_path=str(d.path),
                    tags=list(cached_entry["tags"]),
                    summary=cached_entry["summary"],
                    body=cached_entry["body"],
                    candidate_topics=list(cached_entry["candidate_topics"]),
                    created=cached_entry["created"],
                )
                reused += 1
            else:
                try:
                    content = _read_text(d.path)
                except OSError:
                    if on_note_progress:
                        on_note_progress(i, len(kept), dropped)
                    continue
                note = generate_draft(vault_provider, d.path, content)
                note.created = created

            notes.append(note)
            note_hashes.append(file_hash)
            # Ecriture immediate (avant les liens pour une note nouvelle/modifiee, deja
            # complete pour une note reutilisee du cache) : le vault se remplit note par
            # note sur disque, visible en direct dans Obsidian au lieu d'apparaitre d'un
            # coup a la fin.
            note_path = writer.write(note)
            cache.record_note(d.path, file_hash, note_path, note)
            if on_note_progress:
                on_note_progress(i, len(kept), dropped)

        # Hash de la composition actuelle (fichiers gardes + leur contenu) : inchange par
        # rapport au dernier build reussi => rien de nouveau a lier semantiquement, et
        # graphify n'a rien de nouveau a extraire -- on evite ces deux appels LLM.
        vault_hash = composition_hash(list(zip((n.source_path for n in notes), note_hashes)))
        vault_changed = vault_hash != cache.graphify.get("vault_hash")

        if vault_changed:
            links = propose_links(vault_provider, notes)
            apply_links(notes, links)
            resolve_links(notes)
            for note, file_hash in zip(notes, note_hashes):
                note_path = writer.write(note)  # reecrit chaque note une fois les liens resolus
                cache.record_note(Path(note.source_path), file_hash, note_path, note)
            report(f"Vault genere : {len(notes)} notes dans {vault_dir} ({reused} reutilisees du cache)")
        else:
            report(f"Vault deja a jour : {len(notes)} notes dans {vault_dir}, rien de nouveau depuis le dernier build "
                   "(0 appel LLM)")

        graphify_ran = False
        graphify_out = vault_dir / "graphify-out"
        if not skip_graphify and (vault_changed or not graphify_out.is_dir()):
            notice = graphify_bridge.semantic_extraction_notice()
            if notice:
                report(notice)
            graphify_bridge.run_graphify(vault_dir)
            graphify_ran = True
            report(f"Graphe construit dans {graphify_out}")

        cache.graphify["vault_hash"] = vault_hash
        return BuildResult(decisions, notes, vault_dir, graphify_ran)
    finally:
        cache.save()

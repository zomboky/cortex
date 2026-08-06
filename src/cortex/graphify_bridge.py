"""Pont vers la CLI `graphify` installee (dependance de cortex).

Appel en subprocess plutot qu'import Python de la librairie : la CLI est la
surface publique stable de graphify (pipeline detecter->extraire->construire->
clusteriser->analyser garanti coherent) ; les modules internes (graphify.build,
.cluster, ...) ne sont pas une API tierce stable.

Graphify et cortex ont des configurations LLM totalement independantes :
graphify ne lit que GEMINI_API_KEY/GOOGLE_API_KEY, jamais les variables
CORTEX_*/ANTHROPIC_* de cortex.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class GraphifyError(RuntimeError):
    pass


def graphify_command() -> list[str]:
    exe = shutil.which("graphify")
    if exe:
        return [exe]
    return [sys.executable, "-m", "graphify"]


def semantic_extraction_notice(env: dict[str, str] | None = None) -> str | None:
    """Avertissement a afficher AVANT de lancer graphify si aucune cle Gemini/Google
    n'est definie -- son extraction semantique sera alors limitee au structurel."""
    env = env if env is not None else os.environ
    if env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"):
        return None
    return (
        "Note : GEMINI_API_KEY/GOOGLE_API_KEY non definies -- l'extraction semantique de "
        "graphify sur le vault genere sera limitee a l'extraction structurelle. Definis "
        "l'une de ces variables pour activer l'extraction complete."
    )


def run_graphify(vault_dir: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = [*graphify_command(), str(vault_dir), *(extra_args or [])]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise GraphifyError(f"graphify a echoue (code {result.returncode}) :\n{result.stderr or result.stdout}")
    return result


def run_graphify_query(question: str, graph_dir: Path | None = None, extra_args: list[str] | None = None) -> str:
    """Lance `graphify query "<question>"` avec cwd=graph_dir, puisque graphify
    cherche graphify-out/graph.json relatif au repertoire courant."""
    cmd = [*graphify_command(), "query", question, *(extra_args or [])]
    cwd = str(graph_dir) if graph_dir else None
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)
    if result.returncode != 0:
        raise GraphifyError(f"graphify query a echoue (code {result.returncode}) :\n{result.stderr or result.stdout}")
    return result.stdout

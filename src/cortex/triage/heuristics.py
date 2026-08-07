"""Pre-filtre sans LLM : classe un fichier keep/drop/ambiguous a partir de son chemin,
sa taille et un echantillon de son contenu.

Le signal principal est l'entropie de Shannon de l'echantillon (bits/octet) :
- un texte naturel ou du code se situe dans une bande moyenne (~3.5-5.5 bits/octet)
- un contenu tres repetitif / peu varie (ex. un enorme JSON qui n'est qu'une matrice
  de 0 et de 1) a une entropie BASSE (peu de symboles distincts)
- des donnees binaires/compressees ont une entropie HAUTE (proche de 8, quasi uniforme)
Les deux extremes sont traites comme du bruit, sans jamais appeler le LLM.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

NOISE_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".venv", "venv", ".token-optimizer", "graphify-out", "cortex-out", ".cortex",
}
NOISE_FILENAMES = {"package-lock.json", "yarn.lock", "poetry.lock", "Cargo.lock", "uv.lock"}

AUTO_KEEP_SIZE_CEILING = 200 * 1024  # 200 Ko : texte/code sous ce seuil, garde direct
AMBIGUOUS_SIZE_CEILING = 5 * 1024 * 1024  # 5 Mo : au-dela, ecarte direct (trop gros pour un extrait utile)
NOISE_ENTROPY_SIZE_FLOOR = 50 * 1024  # 50 Ko : sous ce seuil on ne juge pas sur l'entropie seule

LOW_ENTROPY_THRESHOLD = 2.5  # bits/octet -- en dessous : contenu trop repetitif/degenere
HIGH_ENTROPY_THRESHOLD = 7.5  # bits/octet -- au-dessus : quasi-binaire/aleatoire

SAMPLE_BYTES = 16384


class Verdict(str, Enum):
    KEEP = "keep"
    DROP = "drop"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class HeuristicResult:
    verdict: Verdict
    reason: str


def is_noise_path(path: Path) -> bool:
    if set(path.parts) & NOISE_DIR_NAMES:
        return True
    if path.name in NOISE_FILENAMES:
        return True
    return False


def shannon_entropy(sample: bytes) -> float:
    if not sample:
        return 0.0
    counts = Counter(sample)
    length = len(sample)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def classify_bytes(sample: bytes, size: int) -> HeuristicResult:
    """Classification pure a partir d'un echantillon d'octets et de la taille totale.
    Ne touche pas au disque -- utilisable directement avec des octets synthetiques."""
    if size > AMBIGUOUS_SIZE_CEILING:
        return HeuristicResult(
            Verdict.DROP,
            f"fichier de {size} octets, au-dela du plafond ({AMBIGUOUS_SIZE_CEILING} octets)",
        )

    entropy = shannon_entropy(sample)
    if size >= NOISE_ENTROPY_SIZE_FLOOR:
        if entropy < LOW_ENTROPY_THRESHOLD:
            return HeuristicResult(
                Verdict.DROP,
                f"entropie basse ({entropy:.2f} bits/octet) sur un fichier volumineux -- "
                "probable contenu degenere/repetitif (ex. matrice de donnees binaires en texte)",
            )
        if entropy > HIGH_ENTROPY_THRESHOLD:
            return HeuristicResult(
                Verdict.DROP,
                f"entropie haute ({entropy:.2f} bits/octet) sur un fichier volumineux -- "
                "probable contenu binaire/compresse",
            )

    if size <= AUTO_KEEP_SIZE_CEILING:
        return HeuristicResult(Verdict.KEEP, f"contenu textuel, taille sous le plafond ({size} octets)")

    return HeuristicResult(Verdict.AMBIGUOUS, f"contenu textuel mais volumineux ({size} octets)")


def classify_file(path: Path) -> HeuristicResult:
    if is_noise_path(path):
        return HeuristicResult(Verdict.DROP, "chemin correspondant a un motif de bruit connu (build/lock/cache)")

    size = path.stat().st_size
    with path.open("rb") as f:
        sample = f.read(SAMPLE_BYTES)

    return classify_bytes(sample, size)

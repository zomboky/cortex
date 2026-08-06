from __future__ import annotations

import random
from pathlib import Path

from cortex.triage.heuristics import (
    AMBIGUOUS_SIZE_CEILING,
    AUTO_KEEP_SIZE_CEILING,
    NOISE_ENTROPY_SIZE_FLOOR,
    Verdict,
    classify_bytes,
    is_noise_path,
)


def test_normal_text_is_kept() -> None:
    text = (
        "Ceci est une note tout a fait normale, avec des phrases completes, "
        "des mots varies et une structure de langage naturel. " * 20
    ).encode("utf-8")
    result = classify_bytes(text, len(text))
    assert result.verdict == Verdict.KEEP


def test_huge_low_entropy_binary_digit_json_is_dropped() -> None:
    # Simule "un enorme JSON avec des 1 et des 0", l'exemple concret donne par l'utilisateur.
    payload = ("[" + ",".join("0" if i % 2 == 0 else "1" for i in range(100_000)) + "]").encode("utf-8")
    assert len(payload) >= NOISE_ENTROPY_SIZE_FLOOR
    result = classify_bytes(payload, len(payload))
    assert result.verdict == Verdict.DROP
    assert "entropie basse" in result.reason


def test_huge_high_entropy_random_bytes_is_dropped() -> None:
    rng = random.Random(42)
    payload = bytes(rng.randrange(256) for _ in range(NOISE_ENTROPY_SIZE_FLOOR + 1000))
    result = classify_bytes(payload, len(payload))
    assert result.verdict == Verdict.DROP
    assert "entropie haute" in result.reason


def test_oversized_file_is_dropped_regardless_of_content() -> None:
    size = AMBIGUOUS_SIZE_CEILING + 1
    result = classify_bytes(b"du texte normal " * 10, size)
    assert result.verdict == Verdict.DROP


def test_large_but_reasonable_text_is_ambiguous() -> None:
    text = ("Une phrase normale avec du contenu varie et interessant. " * 5000).encode("utf-8")
    size = len(text)
    assert AUTO_KEEP_SIZE_CEILING < size <= AMBIGUOUS_SIZE_CEILING
    result = classify_bytes(text[:16384], size)
    assert result.verdict == Verdict.AMBIGUOUS


def test_small_file_below_entropy_floor_is_kept_even_if_repetitive() -> None:
    payload = b"0,1," * 100  # 400 octets, bien sous NOISE_ENTROPY_SIZE_FLOOR
    result = classify_bytes(payload, len(payload))
    assert result.verdict == Verdict.KEEP


def test_noise_dir_names_are_detected() -> None:
    assert is_noise_path(Path("project/node_modules/pkg/index.js"))
    assert is_noise_path(Path("project/build/output.log"))
    assert is_noise_path(Path("project/package-lock.json"))
    assert not is_noise_path(Path("project/notes/idea.md"))

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_corpus() -> Path:
    return FIXTURES_DIR / "sample_corpus"


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    """La verification de mise a jour (appel reseau vers l'API GitHub) ne doit jamais
    tourner pendant les tests : lente, flaky hors ligne, et hors-sujet pour ces tests."""
    monkeypatch.setenv("CORTEX_SKIP_UPDATE_CHECK", "1")

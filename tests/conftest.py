"""Pytest-Konfiguration und gemeinsame Fixtures.

autouse=True bei set_env_vars bewirkt, dass die Fixture in JEDEM Test
automatisch aktiv ist — kein explizites Einbinden nötig. Das verhindert,
dass Settings() beim Import in src/config.py einen ValidationError wirft,
weil ANTHROPIC_API_KEY in der Test-Umgebung nicht gesetzt ist.
"""

import os


import pytest

# Läuft sofort beim Import von conftest.py (vor jeder Test-Collection) —
# schützt auch Module-Level-Imports von src.config in Testdateien
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setzt Dummy-Umgebungsvariablen für alle Tests.

    monkeypatch von pytest stellt sicher, dass die Variablen nach dem
    Test automatisch zurückgesetzt werden — kein Zustandsleck zwischen Tests.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

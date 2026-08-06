"""Unit-Tests für src/db/embeddings.py.

Der SentenceTransformer wird KOMPLETT gemockt — kein echter Modell-
Download, kein numpy-Rechnen. Der reale Beweis, dass Embeddings
inhaltlich sinnvoll sind, liegt in tests/manual/pgvector_similarity_check.py.
Hier testen wir nur die eigene Logik: Cache und Rückgabetyp.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.db import embeddings


def _fresh_module_state() -> None:
    """Setzt den Modul-Level-Cache zurück, damit Tests unabhängig laufen.

    Ohne diesen Reset würde ein Test, der einen vorherigen Modell-Load
    erlebt hat, den Cache bereits gefüllt vorfinden — der Test auf "wird
    beim ersten Aufruf geladen" wäre dann nicht mehr aussagekräftig.
    """
    embeddings._model = None


@patch("src.db.embeddings.SentenceTransformer")
def test_generate_embedding_gibt_python_liste_zurueck(
    mock_transformer_klasse: MagicMock,
) -> None:
    """generate_embedding() muss list[float] liefern — nicht ndarray.

    pgvector + SQLAlchemy erwartet beim INSERT eine reine Python-Liste;
    ein numpy-Array führt zu einem "unsupported type"-Fehler beim
    Parameter-Binden.
    """
    _fresh_module_state()

    # Mock: das Modell-Objekt hat eine .encode()-Methode, die ein numpy-
    # Array zurückgibt (so verhält sich der echte SentenceTransformer).
    # generate_embedding muss daraus intern eine Liste bauen.
    mock_modell = MagicMock()
    mock_modell.encode.return_value = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    mock_transformer_klasse.return_value = mock_modell

    ergebnis = embeddings.generate_embedding("irgendein text")

    assert isinstance(ergebnis, list)
    # Elementtyp explizit prüfen — .tolist() auf float32-ndarray gibt
    # Python-floats, aber wir wollen es dokumentiert sehen
    assert all(isinstance(x, float) for x in ergebnis)
    # pytest.approx: der echte SentenceTransformer liefert float32,
    # dessen .tolist() erzeugt 64-bit-Werte mit dem float32-Rundungsfehler
    # (0.1 -> 0.10000000149...). Der exakte-Gleichheits-Vergleich würde
    # hier scheitern, obwohl das Verhalten korrekt ist.
    assert ergebnis == pytest.approx([0.1, 0.2, 0.3])
    # encode wurde genau einmal mit dem übergebenen Text aufgerufen
    mock_modell.encode.assert_called_once_with("irgendein text", convert_to_numpy=True)


@patch("src.db.embeddings.SentenceTransformer")
def test_modell_wird_nur_beim_ersten_aufruf_geladen(
    mock_transformer_klasse: MagicMock,
) -> None:
    """Zweiter Aufruf darf SentenceTransformer NICHT erneut instanziieren.

    Kernaussage des Modul-Level-Caches: der teure Load passiert genau
    einmal pro Prozess. Wenn der Cache-Mechanismus kaputt geht, würde
    dieser Test durch call_count=2 sofort auffallen.
    """
    _fresh_module_state()

    mock_modell = MagicMock()
    mock_modell.encode.return_value = np.array([0.0] * 384, dtype=np.float32)
    mock_transformer_klasse.return_value = mock_modell

    embeddings.generate_embedding("erster text")
    embeddings.generate_embedding("zweiter text")
    embeddings.generate_embedding("dritter text")

    # SentenceTransformer(...) genau einmal aufgerufen — trotz drei
    # generate_embedding()-Calls
    assert mock_transformer_klasse.call_count == 1
    # encode() dagegen bei jedem Aufruf, um zu verifizieren dass wir
    # wirklich dasselbe Modell-Objekt wiederverwenden
    assert mock_modell.encode.call_count == 3

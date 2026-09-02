"""Unit-Tests für src/observability.py.

Langfuse-Client UND CallbackHandler werden komplett gemockt — kein
Netzwerk-Call, kein echter Client. Wir testen nur die eigene Logik:
den None-Kurzschluss ohne Keys, die einmalige Initialisierung und den
Modul-Cache (zweiter Aufruf initialisiert NICHT erneut).
"""

from unittest.mock import MagicMock, patch

from src import observability


def _fresh_module_state() -> None:
    """Setzt den Modul-Level-Cache zurück, damit Tests unabhängig laufen.

    Ohne diesen Reset würde ein Test, der die Init bereits erlebt hat,
    den Cache bereits gefüllt vorfinden — der Test auf "wird beim ersten
    Aufruf initialisiert" wäre dann nicht mehr aussagekräftig. Gleiches
    Muster wie in tests/test_embeddings.py::_fresh_module_state.
    """
    observability._initialized = False


def test_get_handler_gibt_none_wenn_keys_fehlen(monkeypatch) -> None:
    """Ohne public_key ist Tracing sauber deaktiviert — None, kein Fehler.

    So bleibt das Projekt lauffähig, auch wenn kein Langfuse-Account
    eingerichtet ist (Zusatzfeature, kein Pflichtbestandteil).
    """
    _fresh_module_state()
    # Beide Keys auf None setzen — die Funktion muss vor jeder Init
    # aussteigen, ohne Langfuse überhaupt anzufassen.
    monkeypatch.setattr(observability.settings, "langfuse_public_key", None)
    monkeypatch.setattr(observability.settings, "langfuse_secret_key", None)

    ergebnis = observability.get_langfuse_handler()

    assert ergebnis is None
    # Cache-Flag darf nicht angefasst worden sein — sonst würde ein
    # späterer Aufruf mit gesetzten Keys die Init überspringen.
    assert observability._initialized is False


@patch("src.observability.CallbackHandler")
@patch("src.observability.Langfuse")
def test_get_handler_initialisiert_und_gibt_handler_zurueck(
    mock_langfuse_klasse: MagicMock,
    mock_callback_klasse: MagicMock,
    monkeypatch,
) -> None:
    """Mit gesetzten Keys: Langfuse(...) wird EINMAL initialisiert, dann Handler."""
    _fresh_module_state()
    monkeypatch.setattr(observability.settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(observability.settings, "langfuse_secret_key", "sk-test")
    monkeypatch.setattr(
        observability.settings, "langfuse_host", "https://cloud.langfuse.com"
    )

    # Return-Value des CallbackHandler-Konstruktors: der zurückgegebene
    # Handler soll unverändert durchgereicht werden.
    mock_handler = MagicMock()
    mock_callback_klasse.return_value = mock_handler

    ergebnis = observability.get_langfuse_handler()

    # Langfuse-Client mit den EXPLIZITEN Werten aus settings — nicht aus
    # os.environ (das ist der Kern des Fixes, den der Docstring beschreibt).
    mock_langfuse_klasse.assert_called_once_with(
        public_key="pk-test",
        secret_key="sk-test",
        host="https://cloud.langfuse.com",
    )
    # Handler wurde ohne Argumente erzeugt — er greift intern auf den
    # oben konfigurierten globalen Client zurück.
    mock_callback_klasse.assert_called_once_with()
    assert ergebnis is mock_handler
    # Cache-Flag ist jetzt True, damit Folgeaufrufe die Init überspringen.
    assert observability._initialized is True


@patch("src.observability.CallbackHandler")
@patch("src.observability.Langfuse")
def test_langfuse_wird_nur_beim_ersten_aufruf_initialisiert(
    mock_langfuse_klasse: MagicMock,
    mock_callback_klasse: MagicMock,
    monkeypatch,
) -> None:
    """Zweiter Aufruf darf Langfuse(...) NICHT erneut instanziieren.

    Kernaussage des Modul-Level-Caches: die teure Client-Konfiguration
    passiert genau einmal pro Prozess. Gleiches Testmuster wie in
    tests/test_embeddings.py::test_modell_wird_nur_beim_ersten_aufruf_geladen.
    """
    _fresh_module_state()
    monkeypatch.setattr(observability.settings, "langfuse_public_key", "pk-test")
    monkeypatch.setattr(observability.settings, "langfuse_secret_key", "sk-test")

    observability.get_langfuse_handler()
    observability.get_langfuse_handler()
    observability.get_langfuse_handler()

    # Langfuse(...) genau einmal — trotz drei Handler-Anforderungen.
    assert mock_langfuse_klasse.call_count == 1
    # CallbackHandler dagegen bei jedem Aufruf frisch — der ist billig
    # und pro Lauf einer sauber, siehe Kommentar in observability.py.
    assert mock_callback_klasse.call_count == 3

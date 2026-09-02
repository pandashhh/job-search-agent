"""Langfuse-Tracing für die LangGraph-Pipeline.

Tracing ist optional: fehlen public_key oder secret_key in der .env,
gibt get_langfuse_handler() ein sauberes None zurück und die Pipeline
läuft unverändert weiter — kein Fehler, kein Overhead.

Warum Modul-Level-Cache statt Neu-Initialisierung pro Aufruf:
Langfuse hält einen globalen Client mit HTTP-Session und internem
Event-Puffer. Wird dieser Client bei jedem Handler-Bezug neu gebaut,
gehen gepufferte Events beim Verwerfen verloren und wir öffnen unnötig
neue HTTP-Verbindungen. Deshalb gleiches Muster wie in
src/db/embeddings.py: einmal initialisieren, danach nur noch den
CallbackHandler wiederverwenden (der nutzt den globalen Client
automatisch).
"""

from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler

from src.config import settings

# Modul-Level-Cache. Initial False, wird beim ersten erfolgreichen
# get_langfuse_handler()-Aufruf einmalig auf True gesetzt und bleibt
# es für die Lebensdauer des Prozesses.
_initialized: bool = False


def get_langfuse_handler() -> CallbackHandler | None:
    """Gibt den Langfuse-CallbackHandler für LangChain/LangGraph zurück.

    Rückgabe:
        - None, falls Tracing nicht konfiguriert ist (public_key ODER
          secret_key fehlt) — Aufrufer soll dann einfach ohne Callback
          weiterarbeiten.
        - CallbackHandler-Instanz, sonst.

    pydantic-settings schreibt .env-Werte nicht nach os.environ (siehe
    evaluate_node-Fix in #8) — CallbackHandler() ohne vorherige explizite
    Langfuse(...)-Initialisierung würde daher versuchen, os.environ zu
    lesen und dort nichts finden. Deshalb hier explizit der Umweg über
    den globalen Client: einmal per Langfuse(...) mit expliziten Werten
    aus settings konfigurieren, danach greift CallbackHandler() darauf zu.
    """
    global _initialized

    # Kurzschluss: ohne Keys kein Tracing. Kein Fehler — das Feature ist
    # bewusst optional (siehe Docstring oben).
    if settings.langfuse_public_key is None or settings.langfuse_secret_key is None:
        return None

    # Beim ERSTEN Aufruf den globalen Langfuse-Client explizit mit den
    # Werten aus settings anlegen — sonst würde CallbackHandler() die
    # os.environ-Variablen suchen, die pydantic-settings gar nicht dorthin
    # schreibt (siehe Docstring oben).
    if not _initialized:
        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _initialized = True

    # Ab hier (auch beim ersten und bei jedem Folgeaufruf): frischer
    # Handler, der intern auf den bereits konfigurierten globalen Client
    # zurückgreift. Einen Handler pro Lauf ist der von Langfuse empfohlene
    # Weg — er ist billig, kein Grund ihn selbst zu cachen.
    return CallbackHandler()


def flush_langfuse() -> None:
    """Erzwingt das Senden gepufferter Trace-Events an Langfuse.

    Langfuse puffert Events intern und sendet sie asynchron — explizites
    flush() stellt sicher, dass Traces auch bei kurzen Prozessen (Skripte,
    einzelne HTTP-Requests) tatsächlich ankommen, bevor der Prozess/Request
    endet.

    No-op, wenn Tracing nicht aktiv ist: ohne vorherige Initialisierung
    gibt es keinen Client zum Flushen.
    """
    if not _initialized:
        return
    get_client().flush()

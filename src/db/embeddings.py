"""Embedding-Generierung für die pgvector-Ähnlichkeitssuche.

Nutzt BAAI/bge-small-en-v1.5 über sentence-transformers — 384 Dimensionen
(deshalb steht in models.py::JobORM.embedding auch Vector(384)). Läuft
komplett lokal: kein API-Call, keine Kosten pro Aufruf. Das Modell wird
beim ersten Aufruf von HuggingFace heruntergeladen (~130 MB) und danach
im lokalen HuggingFace-Cache (~/.cache/huggingface/) abgelegt.

Warum ein Modul-Level-Cache statt Neu-Laden pro Aufruf:
Ein SentenceTransformer wiegt beim Laden knapp eine Sekunde und belegt
mehrere hundert MB Speicher. In anthropic-docs-rag hatten wir genau dieses
Reload-Problem — jede Anfrage lud das Modell frisch, was den Latenz-P95
im Sekundenbereich hielt. Lösung dort: eine Modul-Variable, die beim
ersten Aufruf initialisiert wird. Hier von Anfang an so gebaut, damit
wir das gleiche Ergebnis ohne zweiten Refactor erreichen.
"""

from sentence_transformers import SentenceTransformer

# Konstante Modell-Kennung — an einer Stelle, damit ein späterer Wechsel
# (z.B. auf bge-base) nur eine Zeile berührt.
_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Modul-Level-Cache. Initial None, wird beim ersten _get_model()-Aufruf
# einmalig belegt. Kein threading.Lock: sentence-transformers ist
# thread-safe genug für unseren single-worker-Betrieb, und eine doppelte
# Initialisierung im Race wäre nur teuer, nicht falsch.
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Gibt die (lazy geladene) SentenceTransformer-Instanz zurück.

    Beim ersten Aufruf: HuggingFace-Download oder Load aus dem lokalen
    Cache — kann mehrere Sekunden dauern. Ab dem zweiten Aufruf: reine
    Referenz-Rückgabe aus _model, unter 1 µs.
    """
    global _model
    # None-Check statt try/except — der Fall "Modell schon geladen" ist
    # der 99%-Fall und soll ohne Exception-Overhead durchlaufen
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def generate_embedding(text: str) -> list[float]:
    """Erzeugt ein 384-dimensionales Embedding für den gegebenen Text.

    Rückgabe ist eine reine Python-Liste, kein numpy-Array: pgvector
    zusammen mit SQLAlchemy erwartet ein list[float] beim INSERT (numpy-
    Arrays werden nicht automatisch konvertiert und führen zu einem
    "unsupported type"-Fehler beim Binden des Parameters).
    """
    model = _get_model()
    # convert_to_numpy=True liefert numpy.ndarray — .tolist() macht daraus
    # eine echte, verschachtelungsfreie Python-Liste von floats
    vektor = model.encode(text, convert_to_numpy=True)
    return vektor.tolist()

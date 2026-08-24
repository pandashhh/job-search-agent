"""FastAPI-Dependencies für die HTTP-API.

Aktuell nur die DB-Session — weitere Dependencies (Auth, Rate-Limits)
kommen später.
"""

from typing import Generator

from sqlalchemy.orm import Session

from src.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Öffnet eine SQLAlchemy-Session pro Request und schließt sie zuverlässig.

    Neues Muster gegenüber den LangGraph-Nodes: dort mussten wir jede
    blockierende DB-Operation manuell in asyncio.to_thread() wickeln,
    damit der Event-Loop während einer Query nicht steht (SQLAlchemys
    Standard-Session ist synchron). Hier machen wir das nicht — und
    trotzdem blockiert die API nicht.

    Der Grund: FastAPI erkennt, dass get_db() ein normales "def"
    (synchron) ist, und ruft es automatisch aus einem eigenen
    Thread-Pool auf. Genau das gilt auch für Route-Funktionen, die
    mit "def" (statt "async def") deklariert sind. Deshalb sind unsere
    Routen mit reiner DB-Arbeit ebenfalls "def": FastAPI kümmert sich
    ums Threading, der Event-Loop bleibt frei.

    "async def"-Routen sollten wir dagegen nur nutzen, wenn wir echten
    Async-Code (await ...) brauchen — sonst laufen sie im Event-Loop,
    und ein synchroner DB-Call in einer "async def"-Route würde den
    Loop blockieren.

    yield + try/finally ist das FastAPI-Standardpattern: der yield-Wert
    wird der Route injiziert, der Code nach yield läuft nach Antwort
    oder Exception. So schließt sich die Session zuverlässig, auch
    wenn die Route eine HTTPException wirft.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

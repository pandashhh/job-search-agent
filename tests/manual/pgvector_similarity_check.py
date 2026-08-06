"""Manueller End-to-End-Check: pgvector-Ähnlichkeitssuche mit echten Embeddings.

Legt drei Beispiel-Jobs in der echten Datenbank an (settings.database_url),
erzeugt für jeden ein reales Embedding via generate_embedding() und
führt eine cosine_distance()-Query aus. Kein pytest — direkt mit
`python` ausführen, verursacht Modell-Download beim ersten Lauf und
schreibt/löscht Zeilen in der lokalen DB.

Ausführen:
    python tests/manual/pgvector_similarity_check.py

Voraussetzungen:
    - laufender Postgres unter settings.database_url
    - pgvector-Extension in der DB aktiviert (`CREATE EXTENSION vector;`)
    - Tabellen bereits angelegt (z.B. via pytest-Lauf oder Alembic)

Erwartung, die dieser Lauf beweisen soll:
    Referenz-Job:  "Python Backend Engineer, FastAPI, PostgreSQL"
    - Job 2 ist inhaltlich fast identisch  -> kleinste Distanz (nahe 0)
    - Job 3 ist der Referenz-Job selbst    -> Distanz exakt 0
    - Job "Frontend Developer, React, CSS" -> größte Distanz (klar über 0)
"""

import sys
from pathlib import Path

# Projekt-Root manuell zu sys.path hinzufügen — dieses Skript wird direkt
# via `python` gestartet, nicht über pytest (das nutzt pytest.ini::pythonpath)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.db.base import Base
from src.db.embeddings import generate_embedding

# Alle Modelle importieren, damit Base.metadata sie kennt — sonst legt
# create_all() nur die Modelle an, die zufällig schon irgendwo importiert
# wurden. Noqa, weil die Symbole nicht direkt referenziert werden.
from src.db.models import (  # noqa: F401
    ApplicationStatusORM,
    EvaluationORM,
    FilterRulesORM,
    JobORM,
)


def _make_job(external_id: str, title: str, description: str) -> JobORM:
    """Fabrik für einen JobORM mit gefüllten Pflichtfeldern.

    Nur external_id, title und description variieren — der Rest bekommt
    konstante Dummy-Werte, damit die Instanziierung nicht an einem
    NULL-not-null-Constraint scheitert.
    """
    return JobORM(
        external_id=external_id,
        title=title,
        company="ACME GmbH",
        location="Hamburg",
        job_url=f"https://example.com/{external_id}",
        description=description,
        is_remote=False,
        site="indeed",
        # Embedding hier setzen: generate_embedding lädt beim ersten
        # Aufruf das Modell (~130 MB, dauert einmalig), danach cached
        embedding=generate_embedding(description),
    )


def main() -> None:
    # Engine + Session gegen die echte, konfigurierte Datenbank
    engine = create_engine(settings.database_url)
    # create_all ist idempotent: legt fehlende Tabellen an, lässt bestehende
    # unangetastet. Wichtig, weil die pytest-Fixture (conftest.py) am Ende
    # jeder Test-Session droppt — ohne diesen Aufruf würde das Skript nach
    # einem pytest-Lauf gegen eine leere DB fehlschlagen.
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Drei Jobs: zwei inhaltlich sehr ähnlich (Python/Backend), einer
    # klar anders (Frontend). Externe IDs mit "sim-check-"-Präfix, damit
    # das Cleanup am Ende gezielt nur diese Zeilen trifft.
    job_referenz = _make_job(
        "sim-check-1",
        "Python Backend Engineer",
        "Python Backend Engineer with FastAPI and PostgreSQL. "
        "Build REST APIs, design database schemas, work on async services.",
    )
    job_aehnlich = _make_job(
        "sim-check-2",
        "Backend Software Engineer (Python)",
        "Backend Software Engineer working with Python, FastAPI, and PostgreSQL. "
        "Design and implement REST APIs and async backend services.",
    )
    job_anders = _make_job(
        "sim-check-3",
        "Frontend Developer",
        "Frontend Developer with React, CSS, and TypeScript. "
        "Build responsive user interfaces and design system components.",
    )

    try:
        session.add_all([job_referenz, job_aehnlich, job_anders])
        session.commit()

        # cosine_distance() ist die pgvector-SQLAlchemy-Methode auf der
        # Vector-Spalte. 0.0 = identisch, 2.0 = maximal entgegengesetzt.
        # Wir sortieren aufsteigend, damit der nächste Nachbar zuerst kommt.
        referenz_vektor = job_referenz.embedding
        query = (
            session.query(
                JobORM.title,
                JobORM.embedding.cosine_distance(referenz_vektor).label("distanz"),
            )
            .filter(JobORM.external_id.like("sim-check-%"))
            .order_by("distanz")
        )

        print("Ähnlichkeit zum Referenz-Job (aufsteigend, 0 = identisch):\n")
        for titel, distanz in query.all():
            print(f"  {distanz:.4f}  {titel}")

    finally:
        # Rollback zuerst — falls oben ein commit/flush geworfen hat, ist
        # die Session in "PendingRollback" und lehnt jede weitere Query ab
        session.rollback()
        # Cleanup auch bei Exception — sonst bleiben die Test-Zeilen liegen
        # und der zweite Lauf scheitert am UNIQUE-Constraint auf external_id
        session.query(JobORM).filter(
            JobORM.external_id.like("sim-check-%")
        ).delete(synchronize_session=False)
        session.commit()
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()

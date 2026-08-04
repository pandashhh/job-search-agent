"""Pytest-Konfiguration und gemeinsame Fixtures.

autouse=True bei set_env_vars bewirkt, dass die Fixture in JEDEM Test
automatisch aktiv ist — kein explizites Einbinden nötig. Das verhindert,
dass Settings() beim Import in src/config.py einen ValidationError wirft,
weil ANTHROPIC_API_KEY in der Test-Umgebung nicht gesetzt ist.

DB-Fixtures (db_engine, db_session) sind opt-in: nur Tests, die sie als
Argument anfordern, lösen einen Verbindungsversuch aus. Tests ohne DB
laufen unverändert, auch wenn kein Postgres verfügbar ist.
"""

import os

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings
from src.db.base import Base

# Modelle importieren, damit sie in Base.metadata registriert sind
# (create_all sammelt sonst leere Metadata und legt keine Tabellen an)
from src.db.models import (  # noqa: F401
    ApplicationStatusORM,
    EvaluationORM,
    FilterRulesORM,
    JobORM,
)

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


@pytest.fixture(scope="session")
def db_engine() -> Engine:
    """Erstellt eine SQLAlchemy-Engine gegen settings.database_url und
    legt alle Tabellen an. scope='session' -> genau einmal pro pytest-Lauf.

    Am Ende (nach yield): alle Tabellen wieder droppen, damit derselbe
    lokale DB-Server für andere Zwecke nicht mit Test-Tabellen verschmutzt
    zurückbleibt.

    Voraussetzung: die pgvector-Extension muss in der Ziel-DB bereits
    aktiviert sein (Base.metadata.create_all kann sie nicht selbst
    anlegen, das braucht Superuser). Lokal einmalig via
    `CREATE EXTENSION IF NOT EXISTS vector;` in psql, in CI ist das ein
    eigener Step in ci.yml.
    """
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine: Engine) -> Session:
    """Session pro Test. Nach yield werden alle Zeilen aus den Test-
    Tabellen gelöscht — nicht die Tabellen selbst, damit sich die
    session-scope Fixture nicht neu aufbauen muss.

    DELETE-Reihenfolge respektiert Foreign-Key-Abhängigkeiten:
    erst die Kind-Tabellen (evaluations, application_status), dann jobs;
    filter_rules ist unabhängig, Reihenfolge egal. Ohne diese Reihenfolge
    würde Postgres bei aktiviertem FK-Check den DELETE ablehnen.
    """
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()

    # Cleanup außerhalb der Test-Session, damit auch bei einem im Test
    # nicht committeten State die Tabellen sauber sind
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM evaluations"))
        conn.execute(text("DELETE FROM application_status"))
        conn.execute(text("DELETE FROM jobs"))
        conn.execute(text("DELETE FROM filter_rules"))

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

# Läuft sofort beim Import von conftest.py (vor jeder Test-Collection) —
# schützt auch Module-Level-Imports von src.config in Testdateien
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

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



@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setzt Dummy-Umgebungsvariablen für alle Tests.

    monkeypatch von pytest stellt sicher, dass die Variablen nach dem
    Test automatisch zurückgesetzt werden — kein Zustandsleck zwischen Tests.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture(scope="session")
def db_engine() -> Engine:
    """Erstellt eine SQLAlchemy-Engine gegen settings.test_database_url
    (bewusst NICHT database_url) und legt alle Tabellen an.
    scope='session' -> genau einmal pro pytest-Lauf.

    Am Ende (nach yield): drop_all() räumt alle Tabellen weg. Genau dieser
    drop_all() hat wiederholt die lokale Dev-DB leergemacht (siehe #38),
    solange Fixture und Dev-App auf dieselbe DB zeigten. Deshalb hier
    strikt eine dedizierte Test-DB — komplett getrennt von der DB, die
    settings.database_url referenziert.

    Die pgvector-Extension wird vor create_all() idempotent angelegt
    (CREATE EXTENSION IF NOT EXISTS vector) — dasselbe Prinzip wie in
    der Alembic-Initial-Migration aus #13. Vorteil: eine frisch per
    `createdb job_search_agent_test` angelegte Datenbank funktioniert
    ohne separaten psql-Schritt. Voraussetzung ist, dass der verbundene
    Rollen-User die Extension überhaupt anlegen darf; lokal (peer-Auth
    mit Superuser) und in CI (Service-User "postgres") ist das gegeben.
    """
    engine = create_engine(settings.test_database_url)
    # Extension vor create_all, sonst schlägt der Vector-Spaltentyp
    # beim Anlegen der jobs-Tabelle mit "type vector does not exist" fehl.
    # begin() öffnet eine Transaktion und committet automatisch am Ende.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
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

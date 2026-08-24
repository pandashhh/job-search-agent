"""Tests für die Filter-Rules-Endpoints (GET/PUT /filter-rules).

Wie test_api_jobs.py: TestClient + dependency_overrides[get_db] auf
db_session, echte DB, kontrollierter Ausgangszustand.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.main import app
from src.db.models import FilterRulesORM


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_default_rules(session: Session) -> None:
    """Legt die filter_rules-Zeile an, die die Seed-Migration in Produktion
    beitragen würde. Die db_session-Fixture legt die Tabellen leer an, also
    muss der Test selbst seeden."""
    session.add(
        FilterRulesORM(
            title_blacklist=["Senior", "Lead"],
            max_experience_years=3,
            description_blacklist=["Beratungsprojekte"],
        )
    )
    session.commit()


def test_get_filter_rules_gibt_seed_werte_zurueck(
    client: TestClient, db_session: Session
) -> None:
    """GET liefert die Werte aus der einzigen Tabellen-Zeile."""
    _seed_default_rules(db_session)

    response = client.get("/filter-rules")
    assert response.status_code == 200
    assert response.json() == {
        "title_blacklist": ["Senior", "Lead"],
        "max_experience_years": 3,
        "description_blacklist": ["Beratungsprojekte"],
    }


def test_put_filter_rules_aktualisiert_werte(
    client: TestClient, db_session: Session
) -> None:
    """PUT ersetzt die Werte in der Singleton-Zeile — GET danach zeigt neu."""
    _seed_default_rules(db_session)

    neuer_body = {
        "title_blacklist": ["Manager", "Chef"],
        "max_experience_years": 5,
        "description_blacklist": ["Reisebereitschaft"],
    }
    response = client.put("/filter-rules", json=neuer_body)
    assert response.status_code == 200
    assert response.json() == neuer_body

    # DB-Nachweis: es gibt weiterhin GENAU eine Zeile (Singleton bleibt Singleton)
    zeilen = db_session.query(FilterRulesORM).all()
    assert len(zeilen) == 1
    assert zeilen[0].max_experience_years == 5
    assert zeilen[0].title_blacklist == ["Manager", "Chef"]

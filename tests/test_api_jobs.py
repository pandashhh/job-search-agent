"""Tests für die Job-Endpoints (GET /jobs, PATCH /jobs/{id}/status).

Nutzt FastAPIs TestClient — er wickelt die App wie ein echter HTTP-
Client ein (Request bauen, Response parsen), führt sie aber im selben
Prozess aus, ohne Netzwerk.

app.dependency_overrides[get_db] biegt die DB-Dependency für den
Testlauf auf die db_session-Fixture aus conftest.py um. Damit teilen
sich Test und Route dieselbe Session — der Test kann Daten schreiben,
und die Route findet sie beim Query. Das ist das Standard-FastAPI-
Testpattern für "echte DB, aber kontrollierter Zustand".
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.agent.models import EvaluatedJob, Job, JobEvaluation
from src.api.dependencies import get_db
from src.api.main import app
from src.db.models import ApplicationStatusORM
from src.db.repository import save_evaluated_job

_DUMMY_EMBEDDING = [0.0] * 384


def _make_evaluated_job(
    external_id: str, *, fit_score: float, title: str = "Junior AI Engineer"
) -> EvaluatedJob:
    """Testdaten-Fabrik mit sinnvollen Defaults."""
    return EvaluatedJob(
        job=Job(
            external_id=external_id,
            title=title,
            company="ACME GmbH",
            location="Hamburg",
            job_url=f"https://example.com/{external_id}",
            description="Beschreibung.",
            is_remote=False,
            site="indeed",
        ),
        evaluation=JobEvaluation(
            fit_score=fit_score,
            reasoning="Testbegründung.",
            matched_skills=["Python"],
            missing_skills=[],
        ),
    )


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient mit auf db_session umgebogener get_db-Dependency.

    Ohne den Override würde die Route eine echte, unabhängige Session
    aus SessionLocal() öffnen — Test-Assertions auf db_session würden
    dann Zeilen sehen, die aus einer anderen Transaktion stammen und
    damit unvorhersehbar committet/gerollt zurück sind.
    """
    def _override_get_db():
        # yield derselben Session, kein close() — der Test-Runner
        # räumt die Session am Ende des Tests selbst auf
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        # Aufräumen, damit ein nachfolgender Test nicht denselben
        # Override erbt und dadurch eine bereits geschlossene Session sieht
        app.dependency_overrides.clear()


def test_get_jobs_filtert_nach_min_score(
    client: TestClient, db_session: Session
) -> None:
    """Zwei Jobs mit fit_score 0.8 und 0.3 -> min_score=0.5 gibt nur den
    besseren zurück."""
    save_evaluated_job(
        db_session, _make_evaluated_job("api-job-hi", fit_score=0.8), _DUMMY_EMBEDDING
    )
    save_evaluated_job(
        db_session, _make_evaluated_job("api-job-lo", fit_score=0.3), _DUMMY_EMBEDDING
    )
    db_session.commit()

    response = client.get("/jobs", params={"min_score": 0.5})
    assert response.status_code == 200

    body = response.json()
    external_ids = [job["external_id"] for job in body]
    assert external_ids == ["api-job-hi"]
    # Bewertungsfelder sind flach in der Response — kein evaluation-Nested
    assert body[0]["fit_score"] == 0.8
    assert body[0]["matched_skills"] == ["Python"]


def test_get_jobs_ohne_status_zeigt_neu(
    client: TestClient, db_session: Session
) -> None:
    """Job ohne application_status-Zeile -> status='neu' in der Response."""
    save_evaluated_job(
        db_session, _make_evaluated_job("api-job-no-status", fit_score=0.7), _DUMMY_EMBEDDING
    )
    db_session.commit()

    response = client.get("/jobs")
    body = response.json()

    eintrag = next(j for j in body if j["external_id"] == "api-job-no-status")
    assert eintrag["status"] == "neu"


def test_patch_status_legt_zeile_an(
    client: TestClient, db_session: Session
) -> None:
    """PATCH auf Job ohne bisherigen Status -> 200 + application_status-Zeile
    in der DB nachweisbar."""
    save_evaluated_job(
        db_session, _make_evaluated_job("api-patch-me", fit_score=0.7), _DUMMY_EMBEDDING
    )
    db_session.commit()
    # id aus der DB holen — der Route-Path braucht die interne DB-id, nicht external_id
    from src.db.models import JobORM

    job_id = (
        db_session.query(JobORM).filter_by(external_id="api-patch-me").one().id
    )

    response = client.patch(
        f"/jobs/{job_id}/status", json={"status": "beworben"}
    )
    assert response.status_code == 200
    assert response.json() == {"job_id": job_id, "status": "beworben"}

    # DB-Nachweis: exakt eine Zeile mit dem gesetzten Status
    zeilen = (
        db_session.query(ApplicationStatusORM)
        .filter_by(job_id=job_id)
        .all()
    )
    assert len(zeilen) == 1
    assert zeilen[0].status == "beworben"


def test_patch_status_auf_unbekannten_job_gibt_404(
    client: TestClient,
) -> None:
    """Nicht-existente job_id -> 404, nicht 500 (Repository wirft ValueError,
    Route mappt auf HTTPException)."""
    response = client.patch(
        "/jobs/9999999/status", json={"status": "beworben"}
    )
    assert response.status_code == 404
    assert "9999999" in response.json()["detail"]

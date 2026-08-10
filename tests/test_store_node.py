"""Integrationstests für store_node() aus src/agent/graph.py.

ECHTE Postgres-Verbindung über die db_session-Fixture (aus conftest.py) —
Persistenz wird gegen die echte DB verifiziert, nicht gegen einen
gemockten ORM-State.

generate_embedding IST gemockt, damit die Tests nicht auf das ML-Modell
warten müssen (~130 MB Download beim ersten Aufruf). Der reale
Embedding-Pfad ist über tests/manual/pgvector_similarity_check.py
abgedeckt.

SessionLocal wird auf das Test-Engine umgelenkt (monkeypatch), sonst
würde store_node eine zweite Session gegen dieselbe DB öffnen und die
db_session-Fixture-Cleanups würden sich in die Quere kommen.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.agent.graph import store_node
from src.agent.models import EvaluatedJob, Job, JobEvaluation
from src.db.models import EvaluationORM, JobORM
from src.db.repository import save_evaluated_job

# Fester Dummy-Vektor für das gemockte Embedding. Länge 384 -> passt zur
# Vector(384)-Spalte, Werte inhaltlich egal (Ähnlichkeitssuche wird hier
# nicht getestet, nur der Persistenz-Pfad).
_MOCK_EMBEDDING = [0.1] * 384


def _make_evaluated_job(
    external_id: str, *, fit_score: float = 0.8
) -> EvaluatedJob:
    """Fabrik mit sinnvollen Defaults — nur external_id + fit_score variabel."""
    return EvaluatedJob(
        job=Job(
            external_id=external_id,
            title="Junior AI Engineer",
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


def _base_state(evaluated_jobs: list[EvaluatedJob]) -> dict:
    """Vollständiges AgentState-Dict für Node-Aufrufe."""
    return {
        "search_term": "AI Engineer",
        "location": "Hamburg",
        "raw_jobs": [],
        "filtered_jobs": [],
        "rejected_jobs": [],
        "evaluated_jobs": evaluated_jobs,
        "errors": [],
    }


@pytest.fixture
def store_session_factory(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    """Lenkt src.agent.graph.SessionLocal auf das Test-Engine um.

    Ohne diesen Patch würde store_node den Modul-Level SessionLocal aus
    src.db.session nutzen — der zeigt zwar auf dieselbe DB, aber jede
    Node-Session wäre unabhängig von db_session (der Fixture-Session).
    Die Fixture-Cleanups (DELETE nach jedem Test) räumen zwar trotzdem
    auf, aber wir wollen im Test bewusst dieselbe Engine (also denselben
    Connection Pool) verwenden, um Isolationsfehler auszuschließen.
    """
    TestSessionLocal = sessionmaker(bind=db_engine)
    monkeypatch.setattr("src.agent.graph.SessionLocal", TestSessionLocal)


@pytest.mark.asyncio
async def test_store_node_persistiert_zwei_neue_jobs(
    db_session: Session,
    store_session_factory: None,
) -> None:
    """2 neue EvaluatedJobs -> je 2 Zeilen in jobs und evaluations,
    embedding-Spalte befüllt (nicht None)."""
    jobs = [
        _make_evaluated_job("store-neu-1", fit_score=0.9),
        _make_evaluated_job("store-neu-2", fit_score=0.6),
    ]

    with patch(
        "src.agent.graph.generate_embedding", return_value=_MOCK_EMBEDDING
    ) as mock_emb:
        result = await store_node(_base_state(jobs))

    assert result == {}

    # embedding wurde für BEIDE Jobs berechnet (beide waren neu)
    assert mock_emb.call_count == 2

    # jobs-Tabelle: beide angelegt
    gespeicherte = (
        db_session.query(JobORM)
        .filter(JobORM.external_id.in_(["store-neu-1", "store-neu-2"]))
        .order_by(JobORM.external_id)
        .all()
    )
    assert len(gespeicherte) == 2
    assert [j.external_id for j in gespeicherte] == ["store-neu-1", "store-neu-2"]
    # embedding-Spalte darf nicht None sein und muss zur Vector(384) passen
    for job_orm in gespeicherte:
        assert job_orm.embedding is not None
        assert len(job_orm.embedding) == 384

    # evaluations-Tabelle: 2 Zeilen mit den richtigen Scores
    scores = {
        eval_orm.job_id: eval_orm.fit_score
        for eval_orm in db_session.query(EvaluationORM).all()
    }
    assert scores[gespeicherte[0].id] == 0.9
    assert scores[gespeicherte[1].id] == 0.6


@pytest.mark.asyncio
async def test_store_node_ueberspringt_bereits_bekannten_job(
    db_session: Session,
    store_session_factory: None,
) -> None:
    """1 Job schon in DB, 1 neu -> nur für den neuen Job wird ein Embedding
    berechnet, kein unique-Constraint-Fehler durch den bekannten."""
    # Vorbedingung: einer der beiden Jobs liegt schon in der DB
    schon_da = _make_evaluated_job("store-schon-da", fit_score=0.7)
    save_evaluated_job(db_session, schon_da, _MOCK_EMBEDDING)
    db_session.commit()

    # Beide gehen jetzt durch store_node — der eine schon bekannt, der andere neu
    jobs = [
        _make_evaluated_job("store-schon-da", fit_score=0.99),  # anderer Score, um zu prüfen dass NICHT geupdated wird
        _make_evaluated_job("store-neu", fit_score=0.5),
    ]

    with patch(
        "src.agent.graph.generate_embedding", return_value=_MOCK_EMBEDDING
    ) as mock_emb:
        result = await store_node(_base_state(jobs))

    # Kein Fehler zurückgegeben (kein unique-Constraint-Crash trotz Duplikat)
    assert result == {}

    # Embedding NUR für den neuen Job berechnet — Dedup-Ersparnis
    assert mock_emb.call_count == 1

    # Beide external_ids sind in der DB, aber jeweils nur einmal
    assert (
        db_session.query(JobORM)
        .filter_by(external_id="store-schon-da")
        .count()
        == 1
    )
    assert (
        db_session.query(JobORM).filter_by(external_id="store-neu").count() == 1
    )

    # Der bereits bekannte Job hat noch seinen Original-Score (nicht 0.99)
    orm_schon_da = (
        db_session.query(JobORM).filter_by(external_id="store-schon-da").one()
    )
    assert orm_schon_da.evaluation.fit_score == 0.7


@pytest.mark.asyncio
async def test_store_node_leere_liste_macht_nichts(
    db_session: Session,
    store_session_factory: None,
) -> None:
    """Ohne evaluated_jobs: keine DB-Aktion, kein Fehler, kein Embedding."""
    with patch(
        "src.agent.graph.generate_embedding", return_value=_MOCK_EMBEDDING
    ) as mock_emb:
        result = await store_node(_base_state([]))

    assert result == {}
    # Weder Embedding-Berechnung noch DB-Zeilen entstanden
    mock_emb.assert_not_called()
    assert db_session.query(JobORM).count() == 0

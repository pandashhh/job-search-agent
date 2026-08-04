"""Tests für die SQLAlchemy-ORM-Modelle in src/db/models.py.

Alle Tests brauchen einen laufenden PostgreSQL-Server mit aktivierter
pgvector-Extension — siehe conftest.py::db_engine für Voraussetzungen.
Lokal ohne Postgres schlagen diese Tests fehl; die übrigen (Filter,
Evaluate etc.) bleiben davon unberührt.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models import (
    ApplicationStatusORM,
    EvaluationORM,
    FilterRulesORM,
    JobORM,
)


def _make_job(external_id: str = "ext-1") -> JobORM:
    """Fabrik für einen JobORM mit Pflichtfeldern gefüllt.

    Nur external_id ist pro Test variabel — der Rest bekommt sinnvolle
    Defaults, damit die Instanziierung nicht am ersten Feld scheitert.
    """
    return JobORM(
        external_id=external_id,
        title="Junior AI Engineer",
        company="ACME GmbH",
        location="Hamburg",
        job_url=f"https://example.com/{external_id}",
        description="Beschreibung des Jobs.",
        is_remote=False,
        site="indeed",
    )


def test_job_roundtrip_speichern_und_auslesen(db_session: Session) -> None:
    """Ein JobORM schreiben, committen, wieder auslesen — alle Felder gleich."""
    job = _make_job("ext-roundtrip")
    db_session.add(job)
    db_session.commit()

    geladen = db_session.query(JobORM).filter_by(external_id="ext-roundtrip").one()
    assert geladen.title == "Junior AI Engineer"
    assert geladen.company == "ACME GmbH"
    assert geladen.is_remote is False
    assert geladen.site == "indeed"
    # found_at wird server-seitig gesetzt — muss nach dem Commit einen Wert haben
    assert geladen.found_at is not None


def test_evaluation_relationship_beide_richtungen(db_session: Session) -> None:
    """job.evaluation und evaluation.job müssen sich gegenseitig auflösen —
    Kernindikator, dass back_populates korrekt konfiguriert ist."""
    job = _make_job("ext-eval")
    db_session.add(job)
    db_session.flush()  # damit job.id gesetzt ist, bevor wir sie referenzieren

    eval_ = EvaluationORM(
        job_id=job.id,
        fit_score=0.85,
        reasoning="Guter Match.",
        matched_skills=["Python", "LangGraph"],
        missing_skills=["Airflow"],
    )
    db_session.add(eval_)
    db_session.commit()

    # Aus der Session frisch neu laden, damit wir nicht das Python-Objekt
    # aus dem Identity-Map bekommen (das würde die Frage nicht wirklich testen)
    db_session.expire_all()
    geladen_job = db_session.query(JobORM).filter_by(external_id="ext-eval").one()

    # Vorwärts: Job -> Evaluation
    assert geladen_job.evaluation is not None
    assert geladen_job.evaluation.fit_score == 0.85
    # Rückwärts: Evaluation -> Job
    assert geladen_job.evaluation.job.external_id == "ext-eval"


def test_external_id_unique_constraint(db_session: Session) -> None:
    """Zweiter Job mit derselben external_id muss IntegrityError werfen —
    das ist die DB-Ebene der Dedup-Garantie (Race-safe zwischen parallelen
    Runs, unabhängig vom Application-Code)."""
    db_session.add(_make_job("ext-dup"))
    db_session.commit()

    db_session.add(_make_job("ext-dup"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    # Nach einer fehlgeschlagenen Transaktion muss die Session zurückgerollt
    # werden, sonst hängen alle folgenden Operationen im Fehlerzustand
    db_session.rollback()


def test_application_status_ohne_wert_wirft_integrity_error(db_session: Session) -> None:
    """status ist Pflichtfeld ohne Default (Variante A) -- ein Insert
    ohne expliziten Status muss fehlschlagen, damit nie unklar bleibt,
    ob ein Job schon bearbeitet wurde oder nur vergessen wurde, den
    Status zu setzen."""
    job = _make_job("ext-status")
    db_session.add(job)
    db_session.flush()

    status = ApplicationStatusORM(job_id=job.id)  # status fehlt bewusst
    db_session.add(status)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_filter_rules_json_listen_kommen_als_python_listen_zurueck(
    db_session: Session,
) -> None:
    """JSON-Spalten (matched_skills etc.) müssen echte Python-Listen
    zurückgeben, keinen JSON-Blob-String — sonst müsste jeder Consumer
    manuell json.loads() aufrufen."""
    regeln = FilterRulesORM(
        title_blacklist=["Senior", "Lead"],
        max_experience_years=3,
        description_blacklist=["Beratungsprojekte"],
    )
    db_session.add(regeln)
    db_session.commit()

    db_session.expire_all()
    geladen = db_session.query(FilterRulesORM).one()

    # isinstance-Check ist die Kernaussage — der Wert ist eine Liste,
    # kein String, der aussieht wie eine Liste
    assert isinstance(geladen.title_blacklist, list)
    assert geladen.title_blacklist == ["Senior", "Lead"]
    assert isinstance(geladen.description_blacklist, list)
    assert geladen.max_experience_years == 3

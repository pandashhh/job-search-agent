"""Tests für src/db/repository.py.

Nutzt die db_session-Fixture aus conftest.py — ECHTE Postgres-Verbindung.
Wir wollen genau hier auf das echte Verhalten der DB testen (unique-
Constraint, JOINs, IN-Query), nicht auf eine Mock-Approximation.

Test-Embeddings sind konstruiert (nicht via generate_embedding gebaut),
damit die Tests weder das ML-Modell laden noch von numpy abhängen.
Der reale Beweis, dass Embeddings funktionieren, liegt in
tests/test_pgvector_query.py.
"""

from sqlalchemy.orm import Session

from src.agent.models import EvaluatedJob, Job, JobEvaluation
from src.db.models import EvaluationORM, JobORM
from src.db.repository import (
    get_known_external_ids,
    load_evaluated_job,
    load_evaluated_jobs_batch,
    save_evaluated_job,
)

# Konstanter Dummy-Embedding, groß genug für Vector(384) — der Wert
# ist inhaltlich egal, wir testen nur den Persistenz-Pfad
_DUMMY_EMBEDDING = [0.0] * 384


def _make_evaluated_job(
    external_id: str, *, fit_score: float = 0.8, title: str = "Junior AI Engineer"
) -> EvaluatedJob:
    """Fabrik für einen EvaluatedJob mit Pflichtfeldern gefüllt."""
    return EvaluatedJob(
        job=Job(
            external_id=external_id,
            title=title,
            company="ACME GmbH",
            location="Hamburg",
            job_url=f"https://example.com/{external_id}",
            description="Beschreibung des Jobs.",
            is_remote=False,
            site="indeed",
        ),
        evaluation=JobEvaluation(
            fit_score=fit_score,
            reasoning="Testbegründung.",
            matched_skills=["Python", "LangGraph"],
            missing_skills=["Airflow"],
        ),
    )


def test_save_evaluated_job_legt_beide_tabellen_an(db_session: Session) -> None:
    """Neuer Job -> je eine Zeile in jobs und evaluations, verknüpft über job_id."""
    ej = _make_evaluated_job("repo-new-1", fit_score=0.75)
    save_evaluated_job(db_session, ej, _DUMMY_EMBEDDING)
    db_session.commit()

    # jobs-Zeile prüfen
    job_orm = db_session.query(JobORM).filter_by(external_id="repo-new-1").one()
    assert job_orm.title == "Junior AI Engineer"
    assert job_orm.company == "ACME GmbH"
    # Embedding wurde übernommen — Länge muss zur Vector(384)-Spalte passen
    assert job_orm.embedding is not None
    assert len(job_orm.embedding) == 384

    # evaluations-Zeile prüfen — über den FK job_id verknüpft
    eval_orm = db_session.query(EvaluationORM).filter_by(job_id=job_orm.id).one()
    assert eval_orm.fit_score == 0.75
    assert eval_orm.matched_skills == ["Python", "LangGraph"]
    assert eval_orm.missing_skills == ["Airflow"]


def test_save_evaluated_job_ist_idempotent(db_session: Session) -> None:
    """Zweiter Aufruf mit derselben external_id: kein Fehler, kein Duplikat.

    Ohne die Idempotenz-Prüfung im Repository würde der zweite INSERT am
    unique-Constraint für external_id einen IntegrityError werfen —
    genau das darf hier NICHT passieren.
    """
    ej = _make_evaluated_job("repo-idem", fit_score=0.5)
    save_evaluated_job(db_session, ej, _DUMMY_EMBEDDING)
    db_session.commit()

    # Zweiter Aufruf mit identischer external_id — auch mit anderer
    # fit_score, um zu beweisen dass wir nicht updaten (Semantik: nichts tun)
    ej_zweiter_versuch = _make_evaluated_job("repo-idem", fit_score=0.99)
    save_evaluated_job(db_session, ej_zweiter_versuch, _DUMMY_EMBEDDING)
    db_session.commit()

    # Genau eine jobs-Zeile, mit dem ORIGINAL-fit_score (0.5), nicht 0.99
    jobs = db_session.query(JobORM).filter_by(external_id="repo-idem").all()
    assert len(jobs) == 1
    assert jobs[0].evaluation.fit_score == 0.5


def test_get_known_external_ids_gibt_nur_die_bekannte_teilmenge_zurueck(
    db_session: Session,
) -> None:
    """Batch-Query: 3 IDs abfragen, 2 in DB -> Set mit genau diesen 2 IDs.

    Kernaussage: die Funktion ist die richtige Grundlage für den dedup_node,
    der alle filtered_jobs auf einmal prüft (kein N+1).
    """
    save_evaluated_job(db_session, _make_evaluated_job("repo-known-a"), _DUMMY_EMBEDDING)
    save_evaluated_job(db_session, _make_evaluated_job("repo-known-b"), _DUMMY_EMBEDDING)
    db_session.commit()

    abgefragt = ["repo-known-a", "repo-known-b", "repo-noch-nicht-da"]
    ergebnis = get_known_external_ids(db_session, abgefragt)

    assert ergebnis == {"repo-known-a", "repo-known-b"}


def test_get_known_external_ids_leere_liste_gibt_leeres_set(
    db_session: Session,
) -> None:
    """Frühexit-Pfad: leere Eingabe -> leeres Set, keine DB-Query.

    Kein Bug, wenn die DB-Query stattdessen laufen würde, aber die
    Kurzschluss-Optimierung soll dokumentiert & getestet sein.
    """
    assert get_known_external_ids(db_session, []) == set()


def test_load_evaluated_job_rekonstruiert_originaldaten(
    db_session: Session,
) -> None:
    """Ein zuvor gespeicherter Job muss über load_evaluated_job() feldgenau
    zurückkommen — das ist die Round-Trip-Garantie für dedup_node, der
    bekannte Jobs aus der DB reanimiert und in evaluated_jobs übergibt."""
    original = _make_evaluated_job("repo-roundtrip", fit_score=0.42)
    save_evaluated_job(db_session, original, _DUMMY_EMBEDDING)
    db_session.commit()

    # expire_all() erzwingt einen frischen DB-Load — sonst könnten wir
    # zufällig die Instanz aus der Session-Identity-Map zurückbekommen
    # und der Test würde die DB gar nicht wirklich befragen
    db_session.expire_all()

    geladen = load_evaluated_job(db_session, "repo-roundtrip")

    # Job-Felder
    assert geladen.job.external_id == "repo-roundtrip"
    assert geladen.job.title == "Junior AI Engineer"
    assert geladen.job.company == "ACME GmbH"
    assert geladen.job.location == "Hamburg"
    assert geladen.job.is_remote is False

    # Evaluation-Felder
    assert geladen.evaluation.fit_score == 0.42
    assert geladen.evaluation.matched_skills == ["Python", "LangGraph"]
    assert geladen.evaluation.missing_skills == ["Airflow"]


def test_load_evaluated_jobs_batch_gibt_nur_bekannte_zurueck(
    db_session: Session,
) -> None:
    """Batch-Load: gemischte Liste (bekannt + unbekannt) -> dict nur mit
    den bekannten; unbekannte IDs erscheinen weder als None-Eintrag noch
    als Fehler.

    Das ist der Kontrakt, auf den dedup_node baut: "was nicht im dict
    steht, ist unbekannt und muss durch evaluate_node".
    """
    save_evaluated_job(
        db_session, _make_evaluated_job("repo-batch-a", fit_score=0.4), _DUMMY_EMBEDDING
    )
    save_evaluated_job(
        db_session, _make_evaluated_job("repo-batch-b", fit_score=0.6), _DUMMY_EMBEDDING
    )
    db_session.commit()
    # expire_all(): analog zum load_evaluated_job-Test — sonst käme das
    # Ergebnis potenziell aus dem Identity-Map und die DB wäre unbefragt
    db_session.expire_all()

    ergebnis = load_evaluated_jobs_batch(
        db_session, ["repo-batch-a", "repo-batch-b", "repo-batch-existiert-nicht"]
    )

    # Nur die zwei bekannten sind im dict — unbekannte tauchen nicht auf
    assert set(ergebnis.keys()) == {"repo-batch-a", "repo-batch-b"}
    '''
    Und beide sind vollständig rekonstruiert (selectinload beweist sich hier durch Performance, nicht durch
    Absturzvermeidung -- die Session ist zum Zugriffszeitpunkt noch offen,
    ein DetachedInstanceError wäre auch ohne selectinload nicht aufgetreten.
    Der eigentliche Beweis für den Effekt von selectinload liegt im
c   all_count-Test in test_dedup_node.py (assert_called_once).)
    '''
    assert ergebnis["repo-batch-a"].evaluation.fit_score == 0.4
    assert ergebnis["repo-batch-b"].evaluation.fit_score == 0.6
    assert ergebnis["repo-batch-a"].job.title == "Junior AI Engineer"


def test_load_evaluated_jobs_batch_leere_liste_gibt_leeres_dict(
    db_session: Session,
) -> None:
    """Frühexit-Pfad: leere Eingabe -> leeres dict, kein DB-Roundtrip.

    Verifiziert über einen Query-Counter, dass tatsächlich keine SQL
    ausgeführt wurde — sonst wäre die "if not external_ids"-Guard
    stillschweigend defekt.
    """
    from sqlalchemy import event

    ausgefuehrte_queries: list[str] = []

    def _query_listener(conn, cursor, statement, params, context, executemany):
        ausgefuehrte_queries.append(statement)

    # Auf dem Bind-Engine der Session lauschen — jede SQL landet hier,
    # bevor sie zur DB rausgeht
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _query_listener)
    try:
        ergebnis = load_evaluated_jobs_batch(db_session, [])
    finally:
        event.remove(engine, "before_cursor_execute", _query_listener)

    assert ergebnis == {}
    assert ausgefuehrte_queries == []

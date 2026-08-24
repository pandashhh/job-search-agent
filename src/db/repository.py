"""Repository-Schicht: Übersetzung zwischen Pydantic- und ORM-Welt.

Warum eine explizite Übersetzungsschicht statt Pydantic direkt an die
DB zu binden:
- Pydantic-Modelle (src.agent.models) sind pur — keine DB-Session, keine
  relationship()-Attribute, kein Identity-Map. Sie fließen durch den
  LangGraph-State, werden serialisiert, gemocked, kopiert.
- ORM-Modelle (src.db.models) leben in einer DB-Session, laden bei
  Attributzugriff lazy nach, haben back_populates-Relationships. Sie
  dürfen die Session nicht verlassen — sonst DetachedInstanceError.
- Beide Welten würden bei direktem Coupling gegenseitig Constraints
  auferlegen: Pydantic bräuchte plötzlich Optional-Wrapping für alle
  DB-Felder, ORM bräuchte Pydantic-Validator-Semantik.
Deshalb: bewusst kleine Mapping-Funktionen, jede Grenze klar gezogen.

Alle Funktionen hier committen NICHT selbst. Transaktionsgrenzen sind
Aufgabe des Aufrufers (Node) — nur der kennt den Batch-Kontext (alle
Jobs eines Laufs zusammen, nicht Job für Job).
"""

from sqlalchemy.orm import Session, selectinload

from src.agent.models import EvaluatedJob, FilterRules, Job, JobEvaluation
from src.db.models import (
    ApplicationStatusORM,
    EvaluationORM,
    FilterRulesORM,
    JobORM,
)


def _job_to_orm(job: Job, embedding: list[float] | None) -> JobORM:
    """Baut aus einem Pydantic-Job einen JobORM (noch nicht in der Session).

    embedding wird explizit übergeben, nicht innerhalb dieser Funktion
    berechnet — das Repository soll ML-frei bleiben, sonst zwingen wir
    jeden Test dieser Schicht zum Mocken von sentence-transformers.
    """
    return JobORM(
        external_id=job.external_id,
        title=job.title,
        company=job.company,
        location=job.location,
        job_url=job.job_url,
        description=job.description,
        job_type=job.job_type,
        is_remote=job.is_remote,
        date_posted=job.date_posted,
        min_amount=job.min_amount,
        max_amount=job.max_amount,
        site=job.site,
        embedding=embedding,
    )


def _evaluation_to_orm(
    evaluation: JobEvaluation, job_id: int
) -> EvaluationORM:
    """Baut aus einer Pydantic-JobEvaluation einen EvaluationORM.

    job_id wird separat übergeben — sie ist erst nach dem Flush des
    zugehörigen JobORM bekannt und liegt außerhalb des Pydantic-Modells
    (JobEvaluation kennt weder eine DB noch einen Fremdschlüssel).
    """
    return EvaluationORM(
        job_id=job_id,
        fit_score=evaluation.fit_score,
        reasoning=evaluation.reasoning,
        matched_skills=evaluation.matched_skills,
        missing_skills=evaluation.missing_skills,
    )


def _orm_to_evaluated_job(job_orm: JobORM) -> EvaluatedJob:
    """Baut aus einem JobORM (samt Evaluation-Relationship) einen EvaluatedJob.

    Erwartet, dass job_orm.evaluation bereits geladen ist (via
    relationship-Load oder eager loading). Ohne Evaluation gibt es
    keine sinnvolle EvaluatedJob-Rückgabe — wir werfen dann bewusst
    einen sprechenden Fehler statt still ein None-Feld zu propagieren,
    weil das ein Datenkonsistenz-Bug wäre (jeder gespeicherte Job soll
    auch eine Bewertung haben).
    """
    if job_orm.evaluation is None:
        raise ValueError(
            f"Job '{job_orm.external_id}' hat keine Evaluation in der DB — "
            "Dateninkonsistenz: jeder gespeicherte Job muss eine "
            "zugehörige EvaluationORM-Zeile haben."
        )

    job = Job(
        external_id=job_orm.external_id,
        title=job_orm.title,
        company=job_orm.company,
        location=job_orm.location,
        job_url=job_orm.job_url,
        description=job_orm.description,
        job_type=job_orm.job_type,
        is_remote=job_orm.is_remote,
        date_posted=job_orm.date_posted,
        min_amount=job_orm.min_amount,
        max_amount=job_orm.max_amount,
        site=job_orm.site,
    )
    evaluation = JobEvaluation(
        fit_score=job_orm.evaluation.fit_score,
        reasoning=job_orm.evaluation.reasoning,
        matched_skills=job_orm.evaluation.matched_skills,
        missing_skills=job_orm.evaluation.missing_skills,
    )
    return EvaluatedJob(job=job, evaluation=evaluation)


def get_known_external_ids(
    session: Session, external_ids: list[str]
) -> set[str]:
    """Gibt die Teilmenge zurück, die bereits als JobORM in der DB liegt.

    Bewusst EINE Batch-Query mit IN — der naive Ansatz "pro Job eine
    Query" wäre das klassische N+1-Problem und würde bei 100 gefilterten
    Jobs 100 Roundtrips zur DB machen. So bleibt es ein einziger.

    Leere Eingabe wird abgefangen, damit wir nicht ein leeres IN-Statement
    an Postgres schicken (semantisch ok, syntaktisch je nach Dialekt
    fehleranfällig — und unnötig).
    """
    if not external_ids:
        return set()

    ergebnis = session.query(JobORM.external_id).filter(
        JobORM.external_id.in_(external_ids)
    )
    # ergebnis liefert Tupel [(ext_id,), ...] — flatten via Set-Comprehension
    return {row[0] for row in ergebnis}


def load_evaluated_job(session: Session, external_id: str) -> EvaluatedJob:
    """Lädt einen zuvor gespeicherten Job samt Evaluation aus der DB.

    Nutzt die back_populates-Relationship aus models.py —
    auf job_orm.evaluation zuzugreifen löst eine separate SELECT-Abfrage
    aus (SQLAlchemys Standard lazy='select', kein JOIN).
    Für ein einzelnes Objekt reicht das; für viele Jobs bitte
    load_evaluated_jobs_batch() nutzen (vermeidet N+1).
    """
    job_orm = session.query(JobORM).filter_by(external_id=external_id).one()
    return _orm_to_evaluated_job(job_orm)


def load_evaluated_jobs_batch(
    session: Session, external_ids: list[str]
) -> dict[str, EvaluatedJob]:
    """Lädt mehrere Jobs samt Evaluation in EINER Abfrage-Runde.

    Ersetzt N einzelne load_evaluated_job()-Aufrufe (die je 2 Queries
    brauchen würden — Job holen + separates Nachladen der Evaluation
    über den lazy-Relationship-Zugriff). Statt bei 50 Dedup-Treffern
    100 Roundtrips zu machen, sind es hier zwei: ein SELECT auf jobs
    (IN-Klausel) und ein SELECT auf evaluations (IN-Klausel über die
    gefundenen job_ids, das ist genau was selectinload macht).

    Gibt ein dict external_id -> EvaluatedJob zurück. Externe IDs,
    die nicht in der DB existieren, tauchen im Ergebnis-dict schlicht
    nicht auf (kein Fehler, kein None-Eintrag) — der Aufrufer entscheidet
    selbst, was "unbekannt" bedeutet.
    """
    if not external_ids:
        return {}

    # selectinload(JobORM.evaluation) weist SQLAlchemy an, die zugehörigen
    # EvaluationORMs in EINER separaten IN-Query nachzuladen, statt pro
    # Job einzeln (was der lazy-Default wäre). "selectin" schlägt "joined"
    # hier, weil eine 1:1-Relation kein Duplikat-Risiko bei JOIN hätte,
    # aber selectin auch bei größeren Batches robust bleibt.
    job_orms = (
        session.query(JobORM)
        .options(selectinload(JobORM.evaluation))
        .filter(JobORM.external_id.in_(external_ids))
        .all()
    )
    return {
        job_orm.external_id: _orm_to_evaluated_job(job_orm)
        for job_orm in job_orms
    }


def save_evaluated_job(
    session: Session,
    evaluated_job: EvaluatedJob,
    embedding: list[float] | None,
) -> None:
    """Speichert einen EvaluatedJob idempotent in der DB.

   Idempotenz: falls die external_id schon existiert, wird nichts getan.
    Deckt zuverlässig wiederholte/doppelte Aufrufe INNERHALB desselben Laufs
    ab (z.B. falls ein Job versehentlich zweimal in derselben Job-Liste
    auftaucht). Schützt NICHT vor einer echten Race Condition zwischen zwei
    parallelen Prozessen -- das übernimmt der unique=True-Constraint auf
    external_id in JobORM (siehe #10), der bei einem echten Race eine
    IntegrityError wirft, kein stilles no-op.

    Es passiert KEIN commit() hier. Der Node ruft save_evaluated_job()
    für alle Jobs des Laufs auf und committet einmal am Ende —
    Alles-oder-Nichts pro Lauf.
    """
    # Existenz-Check vor dem Insert — nutzt den unique-Index auf
    # external_id (also billig, keine Full-Scan-Angst)
    schon_vorhanden = (
        session.query(JobORM.id)
        .filter_by(external_id=evaluated_job.job.external_id)
        .first()
    )
    if schon_vorhanden is not None:
        return

    job_orm = _job_to_orm(evaluated_job.job, embedding)
    session.add(job_orm)
    # flush() (nicht commit()) macht job_orm.id sichtbar, ohne die
    # Transaktion zu beenden — wir brauchen die ID gleich für den FK
    session.flush()

    evaluation_orm = _evaluation_to_orm(evaluated_job.evaluation, job_orm.id)
    session.add(evaluation_orm)


# --- filter_rules ---------------------------------------------------------


def get_filter_rules(session: Session) -> FilterRules:
    """Lädt die Singleton-Zeile aus filter_rules als Pydantic-Objekt.

    Die Zeile wird von der Seed-Migration ac7556d5370e beim Migrieren
    angelegt. Fehlt sie trotzdem, ist die Migration nicht sauber gelaufen
    — das ist ein Datenkonsistenz-Bug, kein erwartbarer Zustand, deshalb
    werfen wir hier einen sprechenden Fehler statt still eine Default-
    Regel zu erfinden.
    """
    orm = session.query(FilterRulesORM).first()
    if orm is None:
        raise RuntimeError(
            "filter_rules-Tabelle ist leer — die Seed-Migration "
            "ac7556d5370e wurde nicht angewendet. Bitte "
            "'alembic upgrade head' laufen lassen."
        )
    return FilterRules(
        title_blacklist=orm.title_blacklist,
        max_experience_years=orm.max_experience_years,
        description_blacklist=orm.description_blacklist,
    )


def update_filter_rules(session: Session, rules: FilterRules) -> None:
    """Aktualisiert die bestehende Singleton-Zeile.

    Kein Insert-Fallback: die Zeile existiert seit der Seed-Migration
    immer — würden wir hier ein Insert zulassen, entstünde bei einem
    Bug (z.B. gelöschte Zeile) eine zweite parallele Zeile statt eines
    lauten Fehlers.

    Committet NICHT selbst — gleiche Konvention wie save_evaluated_job:
    der Aufrufer (Route) entscheidet über die Transaktionsgrenze.
    """
    orm = session.query(FilterRulesORM).first()
    if orm is None:
        raise RuntimeError(
            "filter_rules-Tabelle ist leer — die Seed-Migration "
            "ac7556d5370e wurde nicht angewendet."
        )
    orm.title_blacklist = rules.title_blacklist
    orm.max_experience_years = rules.max_experience_years
    orm.description_blacklist = rules.description_blacklist


# --- API-Queries (jobs + application_status) ------------------------------


def list_jobs_with_status(
    session: Session,
    min_score: float,
    status: str | None,
    limit: int,
    offset: int,
) -> list[tuple[JobORM, str]]:
    """Listet bewertete Jobs samt Status für die /jobs-API.

    Query-Struktur:
    - INNER JOIN mit EvaluationORM: jeder gelistete Job hat per Definition
      eine Bewertung (Jobs ohne Evaluation existieren im Betrieb nicht,
      aber der explizite JOIN garantiert das auch dann noch, wenn mal
      ein halbfertiger Datensatz durchrutscht).
    - LEFT OUTER JOIN mit ApplicationStatusORM: die Status-Zeile ist
      optional (Variante A: nur explizit gesetzte Status haben eine
      Zeile), Jobs ohne bekommen "neu" als Default.
    - Filter fit_score >= min_score, optional status = ...
    - Sortiert nach fit_score DESC — Consumer der API will meist die
      besten Matches zuerst.

    Der status-Filter greift NUR auf die Kind-Tabelle, nicht auf den
    Default "neu". Ein Aufruf mit status="neu" gibt deshalb keine Jobs
    zurück, die den Default tragen — bewusste Vereinfachung im ersten
    Wurf, ausbaufähig wenn nötig.
    """
    query = (
        session.query(JobORM, ApplicationStatusORM.status)
        .join(EvaluationORM, EvaluationORM.job_id == JobORM.id)
        .outerjoin(
            ApplicationStatusORM, ApplicationStatusORM.job_id == JobORM.id
        )
        .filter(EvaluationORM.fit_score >= min_score)
    )
    if status is not None:
        query = query.filter(ApplicationStatusORM.status == status)
    query = query.order_by(EvaluationORM.fit_score.desc()).limit(limit).offset(offset)

    # Fehlender application_status -> Default "neu" hier setzen, damit
    # der Route-Code sich nicht mehr um None kümmern muss
    return [
        (job_orm, status_value if status_value is not None else "neu")
        for job_orm, status_value in query.all()
    ]


def upsert_application_status(
    session: Session, job_id: int, status: str
) -> None:
    """Legt einen Status an oder aktualisiert den bestehenden.

    Wirft ValueError, wenn der referenzierte Job nicht existiert —
    sonst würde ein Insert am FK-Constraint mit einer generischen
    IntegrityError sterben. Sprechenderer Fehler = Route kann sauber
    404 statt 500 zurückgeben.

    Committet NICHT selbst.
    """
    # Existiert der Job überhaupt? Reine ID-Query, kein Full-Load
    job_da = session.query(JobORM.id).filter_by(id=job_id).first()
    if job_da is None:
        raise ValueError(f"Job mit id={job_id} existiert nicht.")

    bestehend = (
        session.query(ApplicationStatusORM).filter_by(job_id=job_id).first()
    )
    if bestehend is None:
        session.add(ApplicationStatusORM(job_id=job_id, status=status))
    else:
        bestehend.status = status

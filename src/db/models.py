"""SQLAlchemy-ORM-Modelle für die persistente Job-Datenbank.

Vier Tabellen, jeweils mit klarer Verantwortung:
- jobs: Rohdaten + Embedding (letzteres ab #11 befüllt)
- evaluations: LLM-Bewertung pro Job (1:1)
- filter_rules: aktuelles Regelwerk (Singleton, ersetzt die YAML aus M2)
- application_status: manueller Bewerbungs-Status pro Job (1:1)

Alle Felder mit Mapped[]-Type-Hints (SQLAlchemy 2.0-Stil) — die
Type-Annotation ist zugleich die Spaltendefinition.
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class JobORM(Base):
    """Ein einzelner Job aus einer der Jobbörsen (Indeed, LinkedIn, ...).

    external_id ist der Dedup-Key: bevor ein Job über evaluate_node
    geschickt wird, prüft die Pipeline gegen diese Spalte, ob wir den
    Job schon kennen — spart LLM-Kosten bei wiederkehrenden Anzeigen.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True erzwingt Dedup auf DB-Ebene (Race-safe zwischen zwei
    # parallelen Runs); index=True beschleunigt den Dedup-Lookup
    external_id: Mapped[str] = mapped_column(unique=True, index=True)
    title: Mapped[str]
    company: Mapped[str]
    location: Mapped[str]
    job_url: Mapped[str]
    description: Mapped[str]
    # Optionale Felder: JobSpy liefert diese häufig nicht (siehe
    # docs/jobspy-notes.md), daher Mapped[... | None]
    job_type: Mapped[str | None]
    is_remote: Mapped[bool]
    date_posted: Mapped[str | None]
    min_amount: Mapped[float | None]
    max_amount: Mapped[float | None]
    site: Mapped[str]
    # server_default=func.now() -> Postgres setzt den Timestamp beim
    # INSERT, nicht Python. Kein Zeitzonen-Drift zwischen App-Servern.
    found_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # 384 = Dimension von BAAI/bge-small-en-v1.5 (wie in anthropic-docs-rag).
    # Spalte wird ab Issue #11 tatsächlich befüllt; hier nur reserviert,
    # damit die Migration später keine Tabellen-Rewrite auslöst.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384), nullable=True
    )

    # 1:1-Relationships über die andere Seite (evaluations.job_id ist
    # unique=True); uselist=False sorgt dafür, dass job.evaluation eine
    # einzelne Instanz ist, keine Liste
    evaluation: Mapped["EvaluationORM | None"] = relationship(
        back_populates="job", uselist=False
    )
    application_status: Mapped["ApplicationStatusORM | None"] = relationship(
        back_populates="job", uselist=False
    )


class EvaluationORM(Base):
    """LLM-Bewertung eines Jobs. Pro Job maximal eine Bewertung."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True auf dem FK modelliert die 1:1-Beziehung auf DB-Ebene —
    # verhindert, dass ein Job versehentlich zwei Bewertungen bekommt,
    # unabhängig vom Application-Code
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    fit_score: Mapped[float]
    reasoning: Mapped[str]
    # JSON-Spalten für list[str] — in Postgres nutzt SQLAlchemy JSON
    # unter der Haube (indexierbar, effizient), Rückgabe ist trotzdem
    # eine echte Python-Liste
    matched_skills: Mapped[list[str]] = mapped_column(JSON)
    missing_skills: Mapped[list[str]] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    job: Mapped["JobORM"] = relationship(back_populates="evaluation")


class FilterRulesORM(Base):
    """Aktuelles Filter-Regelwerk. Ersetzt data/filter_rules.yaml aus M2.

    Als Singleton gedacht — eine globale Konfigurationszeile, die
    Filter-Node und Frontend lesen. Kein DB-Constraint (z.B. CHECK auf
    id=1) dafür: bewusste Vereinfachung, wir haben aktuell kein
    Mehrbenutzer-Szenario, das ein Row-per-User-Modell rechtfertigen
    würde.
    """

    __tablename__ = "filter_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_blacklist: Mapped[list[str]] = mapped_column(JSON)
    max_experience_years: Mapped[int]
    description_blacklist: Mapped[list[str]] = mapped_column(JSON)
    # onupdate=func.now() -> Postgres setzt den Timestamp bei jedem
    # UPDATE neu, damit man sieht wann die Regeln zuletzt geändert wurden
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class ApplicationStatusORM(Base):
    """Manueller Bewerbungs-Status pro Job (im Dashboard gepflegt).

    Wird nur angelegt, wenn der Nutzer den Status explizit setzt —
    Jobs ohne Zeile hier gelten implizit als "noch nicht bearbeitet".
    """

    __tablename__ = "application_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True — pro Job höchstens ein Status-Eintrag (1:1)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    # Freier String statt Enum, damit neue Status-Werte (z.B. "abgelehnt-
    # nach-Interview") ohne Migration ergänzt werden können
    status: Mapped[str] 
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    job: Mapped["JobORM"] = relationship(back_populates="application_status")

"""Pydantic-Modelle für die HTTP-API.

Bewusst getrennt von src.agent.models: die API-Schicht braucht Felder,
die den Graph-internen Modellen fremd sind (DB-id, application_status),
und will umgekehrt nicht jede interne Struktur nach außen leaken. Ein
gemeinsames Modell würde beide Seiten unnötig koppeln.

model_config = ConfigDict(from_attributes=True) ist der Pydantic-v2-
Weg für "aus einem SQLAlchemy-Objekt lesen" — ersetzt die alte
Config.orm_mode = True aus Pydantic v1. Wird nur dort gesetzt, wo wir
das Modell direkt mit einem ORM-Objekt füllen wollen.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobResponse(BaseModel):
    """Ein Job wie er in GET /jobs erscheint — Job-Rohdaten + Bewertung + Status."""

    # DB-id ist der Route-Handle für PATCH /jobs/{job_id}/status.
    # external_id bleibt zusätzlich sichtbar (nützlich fürs Frontend, um
    # auf die Quell-Plattform zu verlinken).
    id: int
    external_id: str
    title: str
    company: str
    location: str
    job_url: str
    job_type: str | None = None
    is_remote: bool
    date_posted: str | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    site: str
    found_at: datetime

    # Bewertung ist in der /jobs-Response flach eingebettet (kein
    # verschachtelter "evaluation":{...}-Block) — für die Dashboard-
    # Tabelle einfacher zu konsumieren als ein nested Objekt.
    fit_score: float
    reasoning: str
    matched_skills: list[str]
    missing_skills: list[str]

    # "neu" als Default, wenn keine application_status-Zeile existiert.
    # Das Mapping übernimmt list_jobs_with_status() im Repository, hier
    # ist status also immer ein befüllter String, nie None.
    status: str = "neu"


class StatusUpdateRequest(BaseModel):
    """Body für PATCH /jobs/{job_id}/status."""

    # Freier String bewusst — die DB-Spalte ist ebenfalls String, damit
    # neue Statuswerte ("abgelehnt-nach-Interview") ohne Migration
    # ergänzt werden können.
    status: str = Field(..., min_length=1)


class FilterRulesResponse(BaseModel):
    """Body für GET /filter-rules."""

    title_blacklist: list[str]
    max_experience_years: int
    description_blacklist: list[str]

    model_config = ConfigDict(from_attributes=True)


class FilterRulesUpdateRequest(BaseModel):
    """Body für PUT /filter-rules."""

    title_blacklist: list[str]
    # Muss non-negativ sein — 0 heißt "keine Berufserfahrung erlaubt",
    # negative Werte wären semantisch unsinnig
    max_experience_years: int = Field(..., ge=0)
    description_blacklist: list[str]


class SearchRunRequest(BaseModel):
    """Body für POST /search-runs."""

    search_term: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)


class SearchRunResponse(BaseModel):
    """Zusammenfassung eines abgeschlossenen Suchlaufs.

    Bewusst nur Zählwerte + Fehler, keine Job-Details — die Job-Details
    holt sich das Frontend anschließend über GET /jobs (SoC: der Suchlauf-
    Endpoint macht Persistenz, der Listing-Endpoint macht Query).
    """

    raw_jobs_count: int
    filtered_jobs_count: int
    rejected_jobs_count: int
    evaluated_jobs_count: int
    errors: list[str]

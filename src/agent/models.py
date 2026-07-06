"""Pydantic-Datenmodelle für den Job-Search-Agenten.

Diese Modelle durchlaufen den gesamten LangGraph-Graphen — von der
Rohdaten-Übergabe aus dem MCP-Client bis zur bewerteten Ausgabe.
JobEvaluation dient zugleich als Structured-Output-Schema für Claude Haiku.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Job(BaseModel):
    """Ein einzelner Job, wie er aus dem jobspy-MCP-Server kommt.

    external_id wird in M3 als Dedup-Key in der Postgres-DB verwendet,
    damit bereits bekannte Jobs nicht erneut bewertet werden.
    """

    external_id: str
    title: str
    company: str
    location: str
    job_url: str
    description: str
    # job_type fehlt häufig in Indeed-Ergebnissen — siehe docs/jobspy-notes.md
    job_type: Optional[str] = None
    is_remote: bool
    # date_posted als ISO-String (pandas liefert "2024-01-15T00:00:00.000")
    date_posted: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    # Quell-Plattform: "indeed", "linkedin" o.ä.
    site: str


class RejectedJob(BaseModel):
    """Ein Job, der im Filter-Node ausgeschieden ist, mit Begründung."""

    job: Job
    # Menschenlesbare Begründung, z.B. "title_blacklist: Senior"
    rejection_reason: str


class JobEvaluation(BaseModel):
    """Bewertungsergebnis eines Jobs durch Claude Haiku.

    Dient zugleich als Structured-Output-Schema:
    ChatAnthropic(...).with_structured_output(JobEvaluation) erzwingt,
    dass das Modell exakt dieses Schema zurückgibt.
    """

    # Passungswert 0–1: 1.0 = perfekte Übereinstimmung mit dem Profil
    fit_score: float = Field(..., ge=0.0, le=1.0)
    # Kurze Begründung des Modells für den Score
    reasoning: str
    # Skills aus dem Profil, die die Stelle explizit verlangt
    matched_skills: list[str]
    # Skills, die die Stelle verlangt, aber im Profil fehlen
    missing_skills: list[str]


class EvaluatedJob(BaseModel):
    """Ein Job zusammen mit seiner LLM-Bewertung."""

    job: Job
    evaluation: JobEvaluation

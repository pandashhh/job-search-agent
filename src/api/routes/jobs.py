"""Job-Endpoints: Listing + Status-Update.

Reine DB-Arbeit — daher normale "def"-Routen (nicht "async def"),
FastAPI führt sie im Thread-Pool aus, der Event-Loop bleibt frei.
Siehe src/api/dependencies.py::get_db für den ausführlichen Grund.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas import JobResponse, StatusUpdateRequest
from src.db.repository import list_jobs_with_status, upsert_application_status

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
def get_jobs(
    min_score: float = 0.0,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
) -> list[JobResponse]:
    """Listet bewertete Jobs mit Bewertung und Status.

    Query-Parameter:
    - min_score: nur Jobs mit fit_score >= min_score (Default 0.0 = alle)
    - status_filter: optional exakter Status-String; im Handler-Signature
      "status_filter", weil "status" Namenskollision mit dem FastAPI-
      status-Import wäre — alias="status" sorgt dafür, dass die URL
      trotzdem sauber ?status=... erwartet, nur der interne Python-Name
      bleibt status_filter
    - limit / offset: Standard-Pagination

    Reihenfolge: fit_score DESC — Consumer will typischerweise die
    besten Matches zuerst sehen.
    """
    zeilen = list_jobs_with_status(
        session,
        min_score=min_score,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    # Job-Response manuell zusammensetzen — die Felder kommen aus drei
    # Tabellen (jobs, evaluations, application_status). model_validate
    # auf dem ORM-Objekt allein reicht nicht, weil fit_score & co in
    # einer verwandten Tabelle sitzen.
    return [
        JobResponse(
            id=job_orm.id,
            external_id=job_orm.external_id,
            title=job_orm.title,
            company=job_orm.company,
            location=job_orm.location,
            job_url=job_orm.job_url,
            job_type=job_orm.job_type,
            is_remote=job_orm.is_remote,
            date_posted=job_orm.date_posted,
            min_amount=job_orm.min_amount,
            max_amount=job_orm.max_amount,
            site=job_orm.site,
            found_at=job_orm.found_at,
            fit_score=job_orm.evaluation.fit_score,
            reasoning=job_orm.evaluation.reasoning,
            matched_skills=job_orm.evaluation.matched_skills,
            missing_skills=job_orm.evaluation.missing_skills,
            status=status_wert,
        )
        for job_orm, status_wert in zeilen
    ]


@router.patch("/{job_id}/status", status_code=status.HTTP_200_OK)
def patch_status(
    job_id: int,
    payload: StatusUpdateRequest,
    session: Session = Depends(get_db),
) -> dict:
    """Legt einen application_status an oder aktualisiert den bestehenden.

    Commit ist Aufgabe der Route (nicht des Repositories) — gleiche
    Konvention wie in den Graph-Nodes: Repository-Funktionen bereiten
    Änderungen vor, der Aufrufer setzt die Transaktionsgrenze.
    """
    try:
        upsert_application_status(session, job_id=job_id, status=payload.status)
    except ValueError as e:
        # ValueError = job existiert nicht -> HTTP 404 statt 500
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    session.commit()
    return {"job_id": job_id, "status": payload.status}

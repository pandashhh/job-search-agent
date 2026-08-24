"""Filter-Rules-Endpoints: Regelwerk auslesen und aktualisieren.

Reine DB-Arbeit, also "def" — siehe get_db-Docstring für den Grund.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.agent.models import FilterRules
from src.api.dependencies import get_db
from src.api.schemas import FilterRulesResponse, FilterRulesUpdateRequest
from src.db.repository import get_filter_rules, update_filter_rules

router = APIRouter(prefix="/filter-rules", tags=["filter-rules"])


@router.get("", response_model=FilterRulesResponse)
def get_rules(session: Session = Depends(get_db)) -> FilterRulesResponse:
    """Gibt die aktuelle Singleton-Zeile aus filter_rules zurück."""
    rules = get_filter_rules(session)
    # from_attributes greift auch auf Pydantic-Objekte (Attribut-Zugriff
    # ist identisch), aber ein expliziter Konstruktor ist hier klarer
    return FilterRulesResponse(
        title_blacklist=rules.title_blacklist,
        max_experience_years=rules.max_experience_years,
        description_blacklist=rules.description_blacklist,
    )


@router.put("", response_model=FilterRulesResponse)
def put_rules(
    payload: FilterRulesUpdateRequest,
    session: Session = Depends(get_db),
) -> FilterRulesResponse:
    """Aktualisiert die Singleton-Zeile mit den übergebenen Werten.

    Antwortet mit den neuen Werten — Frontend-Convenience, spart einen
    zweiten GET.
    """
    neue_rules = FilterRules(
        title_blacklist=payload.title_blacklist,
        max_experience_years=payload.max_experience_years,
        description_blacklist=payload.description_blacklist,
    )
    update_filter_rules(session, neue_rules)
    session.commit()
    return FilterRulesResponse(
        title_blacklist=neue_rules.title_blacklist,
        max_experience_years=neue_rules.max_experience_years,
        description_blacklist=neue_rules.description_blacklist,
    )

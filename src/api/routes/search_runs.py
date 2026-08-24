"""Search-Run-Endpoint: startet einen kompletten LangGraph-Lauf.

Dieser Handler ist als einziger "async def" — er ruft graph.ainvoke()
direkt via await auf. Kein Depends(get_db): der Graph verwaltet seine
DB-Sessions über die einzelnen Nodes (SessionLocal() innerhalb der
Node), damit jede Node ihren eigenen, kurzlebigen Kontext hat.

Der Endpoint blockiert bis der komplette Lauf fertig ist — bewusste
Vereinfachung im ersten Wurf. Ein Job-Scraping-Lauf dauert typisch
30 s bis wenige Minuten; solange das ein interner Nutzer im Dashboard
anstößt und wartet, ist das ok. Bei größeren Läufen oder öffentlicher
Auslage später auf FastAPI BackgroundTasks (fire-and-forget) oder eine
richtige Queue (Cloud Tasks / Redis + rq) wechseln.
"""

from fastapi import APIRouter

from src.agent.graph import build_graph
from src.api.schemas import SearchRunRequest, SearchRunResponse

router = APIRouter(prefix="/search-runs", tags=["search-runs"])


@router.post("", response_model=SearchRunResponse)
async def start_search_run(payload: SearchRunRequest) -> SearchRunResponse:
    """Kompiliert den Graphen und lässt ihn synchron durchlaufen."""
    graph = build_graph()

    # Vollständiger Initial-State: alle List-Keys müssen vorhanden sein,
    # sonst wirft LangGraph beim ersten Zugriff KeyError
    ergebnis = await graph.ainvoke(
        {
            "search_term": payload.search_term,
            "location": payload.location,
            "raw_jobs": [],
            "filtered_jobs": [],
            "rejected_jobs": [],
            "evaluated_jobs": [],
            "errors": [],
        }
    )

    return SearchRunResponse(
        raw_jobs_count=len(ergebnis["raw_jobs"]),
        filtered_jobs_count=len(ergebnis["filtered_jobs"]),
        rejected_jobs_count=len(ergebnis["rejected_jobs"]),
        evaluated_jobs_count=len(ergebnis["evaluated_jobs"]),
        errors=ergebnis["errors"],
    )

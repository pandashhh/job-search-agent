"""FastAPI-Einstiegspunkt für den Job-Search-Agenten.

Start (lokal):
    uvicorn src.api.main:app --reload

In Produktion später über Gunicorn+uvicorn-Workers oder Cloud Run.
"""

from fastapi import FastAPI

from src.api.routes import filter_rules, jobs, search_runs

app = FastAPI(
    title="Job Search Agent API",
    description=(
        "HTTP-API vor dem LangGraph-Agenten: Jobs listen, Filter-Regeln "
        "pflegen, Suchläufe starten."
    ),
)

# Router in stabiler Reihenfolge einhängen — irrelevant für Routing,
# aber die generierte OpenAPI-Doku spiegelt die Reihenfolge wider.
app.include_router(jobs.router)
app.include_router(filter_rules.router)
app.include_router(search_runs.router)


@app.get("/", tags=["health"])
def health() -> dict[str, str]:
    """Simpler Liveness-Check — nutzt keine DB, damit Container-Orchestrator
    (Cloud Run, kubernetes) auch bei DB-Ausfall unterscheiden können, ob
    der Prozess selbst noch antwortet."""
    return {"status": "ok"}

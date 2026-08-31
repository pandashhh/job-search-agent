"""FastAPI-Einstiegspunkt für den Job-Search-Agenten.

Start (lokal):
    uvicorn src.api.main:app --reload

In Produktion später über Gunicorn+uvicorn-Workers oder Cloud Run.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import filter_rules, jobs, search_runs

app = FastAPI(
    title="Job Search Agent API",
    description=(
        "HTTP-API vor dem LangGraph-Agenten: Jobs listen, Filter-Regeln "
        "pflegen, Suchläufe starten."
    ),
)

# CORS: nötig, weil Frontend (Vite-Dev-Server auf Port 5173) und API
# (uvicorn auf Port 8000) im Dev-Betrieb unterschiedliche Origins sind
# — der Browser blockiert Cross-Origin-Requests sonst per Same-Origin-
# Policy. In Produktion werden Frontend + API typischerweise hinter
# demselben Origin ausgeliefert (Reverse Proxy), dann kann diese
# Middleware raus oder auf die tatsächliche Prod-Domain restricted
# werden.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
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

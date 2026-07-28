"""LangGraph-Graph-Definition für den Job-Search-Agenten.

Topologie: START → search → filter → evaluate → store → END
Strikt linear, keine Conditional Edges — leere Ergebnisse laufen als
leere Listen durch die restlichen Nodes (jeder Node behandelt sie als No-op).
"""

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.filters import filter_job, load_filter_rules
from src.agent.models import Job, RejectedJob
from src.agent.state import AgentState
from src.mcp_client.jobspy_client import search_jobs_via_mcp


async def search_node(state: AgentState) -> dict:
    """Ruft den jobspy-MCP-Server auf und mappt die Ergebnisse auf Job-Objekte.

    Fehlerbehandlung auf zwei Ebenen:
    - Komplettausfall (Server nicht erreichbar, RuntimeError): kein raw_jobs
      im Rückgabe-Dict, Fehler landet in errors.
    - Einzelner kaputter Job-Dict: dieser Job wird übersprungen, die
      restlichen Jobs werden trotzdem verarbeitet.
    """
    mapping_errors: list[str] = []

    try:
        raw_dicts = await search_jobs_via_mcp(
            search_term=state["search_term"],
            location=state["location"],
        )
    except Exception as e:
        # Kein raw_jobs im Rückgabe-Dict — LangGraph lässt den bestehenden
        # State-Wert unverändert, wenn ein Key fehlt
        return {"errors": state["errors"] + [f"Search-Node: {e}"]}

    jobs: list[Job] = []
    for raw in raw_dicts:
        try:
            # Explizites Mapping nötig: JobSpy nennt das Feld "id",
            # unser Modell "external_id" — **raw würde crashen
            job = Job(
                external_id=raw["id"],
                title=raw["title"],
                company=raw["company"],
                location=raw["location"],
                job_url=raw["job_url"],
                description=raw["description"],
                is_remote=raw["is_remote"],
                site=raw["site"],
                # Optionale Felder: .get() mit None-Default, da JobSpy
                # diese Felder häufig weglässt (siehe docs/jobspy-notes.md)
                job_type=raw.get("job_type"),
                date_posted=raw.get("date_posted"),
                min_amount=raw.get("min_amount"),
                max_amount=raw.get("max_amount"),
            )
            jobs.append(job)
        except Exception as e:
            # Einen kaputten Eintrag überspringen, nicht den ganzen Lauf stoppen
            job_id = raw.get("id", "<unbekannt>")
            mapping_errors.append(f"Search-Node: Job '{job_id}' übersprungen: {e}")

    result: dict = {"raw_jobs": jobs}
    if mapping_errors:
        result["errors"] = state["errors"] + mapping_errors
    return result


async def filter_node(state: AgentState) -> dict:
    """Wendet Filterregeln aus data/filter_rules.yaml auf raw_jobs an.

    Ablauf:
    1. Regeln einmal pro Node-Aufruf laden (nicht pro Job — spart I/O)
    2. Über raw_jobs iterieren, filter_job() als Entscheider aufrufen
    3. Bei None: Job durchgelassen -> filtered_jobs
       Bei Grund: Job in RejectedJob mit rejection_reason verpacken

    Leerer raw_jobs-State ist explizit erlaubt (Search-Node kann bei
    einem Fehler ohne Ergebnisse ankommen) — die Schleife läuft dann
    einfach nicht, beide Listen bleiben leer, kein Fehler.
    """
    # Regeln einmal laden — später (M3) könnten hier DB-Regeln kommen
    rules = load_filter_rules()

    filtered_jobs: list[Job] = []
    rejected_jobs: list[RejectedJob] = []

    for job in state["raw_jobs"]:
        reason = filter_job(job, rules)
        if reason is None:
            # Kein Ablehnungsgrund gefunden -> Job besteht den Filter
            filtered_jobs.append(job)
        else:
            # Grund vorhanden -> Job mit Begründung verpacken
            rejected_jobs.append(RejectedJob(job=job, rejection_reason=reason))

    return {"filtered_jobs": filtered_jobs, "rejected_jobs": rejected_jobs}


async def evaluate_node(state: AgentState) -> dict:
    """Bewertet jeden gefilterten Job via Claude Haiku (Structured Output).

    TODO (#8): ChatAnthropic(...).with_structured_output(JobEvaluation) nutzen,
    Profil aus data/profile.yaml laden, sequenziell über filtered_jobs iterieren,
    Ergebnisse als list[EvaluatedJob] in evaluated_jobs schreiben.
    """
    return {}


async def store_node(state: AgentState) -> dict:
    """Schreibt evaluated_jobs als JSON nach data/results/{timestamp}.json.

    TODO (#8 Stub / #9): store_results() implementieren. Interface bleibt
    erhalten — in M3 wird die Implementierung auf Postgres umgestellt,
    ohne dass dieser Node verändert werden muss.
    """
    return {}


def build_graph() -> CompiledStateGraph:
    """Baut den kompilierten LangGraph-Graphen und gibt ihn zurück.

    Aufruf:
        graph = build_graph()
        result = await graph.ainvoke({"search_term": "...", "location": "..."})
    """
    builder = StateGraph(AgentState)

    # Nodes registrieren
    builder.add_node("search_node", search_node)
    builder.add_node("filter_node", filter_node)
    builder.add_node("evaluate_node", evaluate_node)
    builder.add_node("store_node", store_node)

    # Lineare Kanten: START → search → filter → evaluate → store → END
    builder.add_edge(START, "search_node")
    builder.add_edge("search_node", "filter_node")
    builder.add_edge("filter_node", "evaluate_node")
    builder.add_edge("evaluate_node", "store_node")
    builder.add_edge("store_node", END)

    return builder.compile()

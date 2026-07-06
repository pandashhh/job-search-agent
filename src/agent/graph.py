"""LangGraph-Graph-Definition für den Job-Search-Agenten.

Topologie: START → search → filter → evaluate → store → END
Strikt linear, keine Conditional Edges — leere Ergebnisse laufen als
leere Listen durch die restlichen Nodes (jeder Node behandelt sie als No-op).
"""

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from src.agent.state import AgentState


async def search_node(state: AgentState) -> dict:
    """Startet den jobspy-MCP-Server und ruft search_jobs() auf.

    TODO (#6): MCP-Client aus src/mcp_client/jobspy_client.py nutzen,
    Ergebnisse als list[Job] in raw_jobs schreiben.
    """
    return {}


async def filter_node(state: AgentState) -> dict:
    """Wendet Filterregeln aus data/filter_rules.yaml auf raw_jobs an.

    TODO (#7): load_filter_rules() implementieren, title_blacklist und
    max_experience_years-Regex gegen title/description prüfen,
    gefilterte Jobs in filtered_jobs, aussortierte in rejected_jobs schreiben.
    """
    return {}


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

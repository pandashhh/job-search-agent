"""LangGraph-State für den Job-Search-Agenten.

TypedDict statt Pydantic, weil LangGraph intern dict-Operationen auf dem
State ausführt (partielles Updaten via Node-Rückgaben). Pydantic-Modelle
leben in models.py und werden als Feldtypen referenziert.
"""

from typing import TypedDict

from src.agent.models import EvaluatedJob, Job, RejectedJob


class AgentState(TypedDict):
    """Gemeinsamer Zustand, der durch alle vier Nodes fließt.

    Jeder Node gibt ein partielles dict zurück — LangGraph merged die
    Rückgabe in den bestehenden State. Felder, die ein Node nicht
    verändert, bleiben unverändert.
    """

    # Suchparameter — werden vom Aufrufer gesetzt, nicht vom Graphen verändert
    search_term: str
    location: str

    # Rohergebnisse aus dem MCP-Server (Search-Node befüllt dieses Feld)
    raw_jobs: list[Job]

    # Jobs, die den Filter-Node bestanden haben
    filtered_jobs: list[Job]

    # Jobs, die der Filter-Node ausgeschieden hat (mit Begründung)
    rejected_jobs: list[RejectedJob]

    # Jobs nach LLM-Bewertung durch den Evaluate-Node
    evaluated_jobs: list[EvaluatedJob]

    # Sammlung nicht-fataler Fehler aus allen Nodes (Node läuft weiter,
    # Fehler wird hier eingetragen statt den Graphen zu stoppen)
    errors: list[str]

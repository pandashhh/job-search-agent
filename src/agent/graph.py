"""LangGraph-Graph-Definition für den Job-Search-Agenten.

Topologie: START → search → filter → dedup → evaluate → store → END
Strikt linear, keine Conditional Edges — leere Ergebnisse laufen als
leere Listen durch die restlichen Nodes (jeder Node behandelt sie als No-op).

dedup wurde vor evaluate eingefügt (Issue #12), damit bereits bekannte
Jobs nicht erneut per LLM bewertet werden — spart Anthropic-Kosten und
Latenz. Bekannte Jobs werden aus der DB rekonstruiert und direkt in
evaluated_jobs übernommen; nur wirklich neue Jobs erreichen evaluate.
"""

import asyncio

from langchain_anthropic import ChatAnthropic
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from src.agent.evaluation import build_system_prompt, load_profile
from src.agent.filters import filter_job, load_filter_rules
from src.agent.models import EvaluatedJob, Job, JobEvaluation, RejectedJob
from src.agent.state import AgentState
from src.config import settings
from src.db.embeddings import generate_embedding
from src.db.repository import (
    get_known_external_ids,
    load_evaluated_job,
    save_evaluated_job,
)
from src.db.session import SessionLocal
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


def _dedup_split(
    session: Session, filtered_jobs: list[Job]
) -> tuple[list[Job], list[EvaluatedJob]]:
    """Synchroner DB-Teil des dedup_node — via to_thread aufgerufen.

    Gibt zwei Listen zurück:
    - unbekannte Jobs (bleiben in filtered_jobs für evaluate_node)
    - bereits bewertete Jobs (werden an evaluated_jobs angehängt)
    Alles in EINER Batch-Query auf get_known_external_ids, kein N+1.
    """
    externe_ids = [job.external_id for job in filtered_jobs]
    bekannt = get_known_external_ids(session, externe_ids)

    unbekannte: list[Job] = []
    aus_db_geladen: list[EvaluatedJob] = []
    for job in filtered_jobs:
        if job.external_id in bekannt:
            # Aus der DB reanimieren — spart den Anthropic-Call
            aus_db_geladen.append(load_evaluated_job(session, job.external_id))
        else:
            unbekannte.append(job)
    return unbekannte, aus_db_geladen


async def dedup_node(state: AgentState) -> dict:
    """Trennt bekannte von unbekannten Jobs — spart LLM-Bewertungskosten.

    Ablauf:
    1. Bei leerem filtered_jobs sofort raus, keine DB-Verbindung nötig
    2. Session öffnen, blockierenden DB-Teil in einem Worker-Thread
       ausführen (SQLAlchemy-Session ist synchron; ohne to_thread würde
       der ganze Event-Loop während der DB-Query blockieren — bei
       parallelen Runs merkbar; siehe Review zu Issue #11)
    3. Bekannte Jobs aus der DB als EvaluatedJob rekonstruieren und
       an state["evaluated_jobs"] anhängen
    4. Nur unbekannte bleiben in filtered_jobs -> evaluate_node arbeitet
       ausschließlich auf neuen Jobs
    """
    if not state["filtered_jobs"]:
        # Nichts zu tun — kein Session-Aufbau, kein State-Update
        return {}

    session = SessionLocal()
    try:
        unbekannte, aus_db = await asyncio.to_thread(
            _dedup_split, session, state["filtered_jobs"]
        )
    finally:
        session.close()

    return {
        "filtered_jobs": unbekannte,
        # Anhängen, nicht überschreiben — evaluate_node hängt seine
        # neuen Bewertungen ebenfalls an (siehe Kommentar dort)
        "evaluated_jobs": state["evaluated_jobs"] + aus_db,
    }


async def evaluate_node(state: AgentState) -> dict:
    """Bewertet jeden gefilterten Job via Claude Haiku (Structured Output).

    Ablauf:
    1. Bei leerem filtered_jobs sofort raus — kein API-Call, spart Kosten
    2. Profil einmal laden, System-Prompt einmal bauen (nicht pro Job)
    3. ChatAnthropic mit with_structured_output(JobEvaluation) — erzwingt,
       dass das Modell exakt unser Pydantic-Schema zurückgibt
    4. SEQUENZIELL über filtered_jobs iterieren (m2-design.md: keine
       Parallelisierung im ersten Wurf; asyncio.gather+Semaphore kommt später)
    5. Pro Job: bei API-Fehler den Job überspringen, Fehler in errors
       sammeln, restliche Jobs trotzdem bewerten (kein Alles-oder-Nichts)

    WICHTIG (ab #12): Rückgabe hängt an state["evaluated_jobs"] AN,
    überschreibt nicht. Grund: dedup_node befüllt evaluated_jobs bereits
    mit rekonstruierten bekannten Jobs — würden wir überschreiben, gingen
    diese Einträge verloren.
    """
    # Kurzschluss: keine neuen Jobs -> keine neuen Bewertungen, State
    # bleibt wie er ist (dedup_node kann evaluated_jobs gefüllt haben)
    if not state["filtered_jobs"]:
        return {}

    profile = load_profile()
    system_prompt = build_system_prompt(profile)

    # with_structured_output bindet das Pydantic-Schema an das Modell.
    # Rückgabe von ainvoke() ist dann direkt eine JobEvaluation-Instanz.
    chat = ChatAnthropic(model=settings.evaluation_model,anthropic_api_key=settings.anthropic_api_key,)
    chain = chat.with_structured_output(JobEvaluation)

    neue_bewertungen: list[EvaluatedJob] = []
    new_errors: list[str] = []

    for job in state["filtered_jobs"]:
        # Beschreibung als Guard gegen Ausreißer-Anzeigen kürzen —
        # 8000 Zeichen (Default) reichen für 99% der Anzeigen
        description = job.description[: settings.max_description_chars]

        # User-Message wortwörtlich strukturiert, damit das Modell die
        # Felder klar unterscheiden kann (nicht als JSON-Blob mit
        # Escaping-Risiko)
        user_message = (
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location}\n"
            f"Job Type: {job.job_type or 'nicht angegeben'}\n"
            f"Remote: {'ja' if job.is_remote else 'nein'}\n"
            f"\n"
            f"Description:\n{description}"
        )

        try:
            evaluation = await chain.ainvoke(
                [
                    ("system", system_prompt),
                    ("human", user_message),
                ]
            )
            neue_bewertungen.append(EvaluatedJob(job=job, evaluation=evaluation))
        except Exception as e:
            # Einen kaputten Bewertungs-Call überspringen, nicht den
            # ganzen Node stoppen — die anderen Jobs sollen trotzdem
            # bewertet werden
            new_errors.append(
                f"Evaluate-Node: Job '{job.external_id}' übersprungen: {e}"
            )

    # Anhängen an das, was dedup_node bereits reingelegt hat
    result: dict = {"evaluated_jobs": state["evaluated_jobs"] + neue_bewertungen}
    if new_errors:
        result["errors"] = state["errors"] + new_errors
    return result


def _store_all(session: Session, evaluated_jobs: list[EvaluatedJob]) -> None:
    """Synchroner Persistenz-Teil des store_node — via to_thread aufgerufen.

    Ein einziger commit() am Ende: Alles-oder-Nichts pro Lauf. Fällt
    ein Insert oder ein Embedding-Call in der Mitte um, rollt der Node-
    Code (oben) per Exception-Handler zurück.

    Embedding-Berechnung nur für tatsächlich neue Jobs — Dedup-Hits sind
    schon in der DB und haben ein Embedding, für sie ~130 MB Modell-CPU
    zu verbrennen wäre Verschwendung (Punkt aus Review #11, jetzt gelöst).
    """
    externe_ids = [ej.job.external_id for ej in evaluated_jobs]
    bekannt = get_known_external_ids(session, externe_ids)

    for evaluated_job in evaluated_jobs:
        if evaluated_job.job.external_id in bekannt:
            # save_evaluated_job() wäre schon idempotent, aber wir wollen
            # das teure generate_embedding() explizit überspringen
            continue
        # Kombiniert Job-Titel + Beschreibung — der Titel trägt viel
        # semantisches Gewicht und würde in einer reinen Description-
        # Embedding untergehen
        embedding_text = f"{evaluated_job.job.title}\n{evaluated_job.job.description}"
        embedding = generate_embedding(embedding_text)
        save_evaluated_job(session, evaluated_job, embedding)

    session.commit()


async def store_node(state: AgentState) -> dict:
    """Persistiert evaluated_jobs in Postgres (jobs + evaluations).

    Ersetzt die JSON-Datei-Persistenz aus M2 (settings.results_dir bleibt
    aus Rückwärts-Freundlichkeit ungenutzt in der Config stehen). Ablauf:
    1. Bei leerer Liste: kein Session-Aufbau, kein Fehler, {} zurück
    2. Session öffnen, in einem Worker-Thread:
       a. bekannte external_ids per Batch-Query holen
       b. für jeden neuen Job Embedding berechnen (blockierender ML-Call
          — deshalb im Thread, um den Event-Loop frei zu halten)
       c. via save_evaluated_job() speichern (idempotent)
       d. EIN gemeinsamer commit am Ende
    3. Bei Exception: rollback, Fehler in errors, kein Crash — gleiche
       Philosophie wie Search- und Evaluate-Node
    """
    if not state["evaluated_jobs"]:
        return {}

    session = SessionLocal()
    try:
        await asyncio.to_thread(_store_all, session, state["evaluated_jobs"])
        return {}
    except Exception as e:
        # rollback ebenfalls im Thread — session.rollback ist synchron
        # und würde sonst gegen den Session-State (PendingRollback) laufen
        await asyncio.to_thread(session.rollback)
        return {"errors": state["errors"] + [f"Store-Node: {e}"]}
    finally:
        session.close()


def build_graph() -> CompiledStateGraph:
    """Baut den kompilierten LangGraph-Graphen und gibt ihn zurück.

    Topologie: START → search → filter → dedup → evaluate → store → END
    dedup sitzt bewusst vor evaluate, damit bekannte Jobs nicht durch den
    (kostenpflichtigen) LLM-Call laufen.

    Aufruf:
        graph = build_graph()
        result = await graph.ainvoke({"search_term": "...", "location": "..."})
    """
    builder = StateGraph(AgentState)

    # Nodes registrieren
    builder.add_node("search_node", search_node)
    builder.add_node("filter_node", filter_node)
    builder.add_node("dedup_node", dedup_node)
    builder.add_node("evaluate_node", evaluate_node)
    builder.add_node("store_node", store_node)

    # Lineare Kanten: START → search → filter → dedup → evaluate → store → END
    builder.add_edge(START, "search_node")
    builder.add_edge("search_node", "filter_node")
    builder.add_edge("filter_node", "dedup_node")
    builder.add_edge("dedup_node", "evaluate_node")
    builder.add_edge("evaluate_node", "store_node")
    builder.add_edge("store_node", END)

    return builder.compile()

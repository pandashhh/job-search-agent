"""End-to-End-Test für den kompletten LangGraph-Graphen.

Dieser Test ist die automatisierte, gemockte Entsprechung von
tests/manual/full_agent_run_check.py — letzteres verifiziert mit
echten Daten (echter MCP-Server, echte Anthropic-API), dass die
Pipeline inhaltlich funktioniert; dieser Test hier verifiziert das
Zusammenspiel aller fünf Nodes deterministisch und ohne API-Kosten.

Mocking-Grenze bewusst eng gezogen: MCP-Client, ChatAnthropic-LLM und
generate_embedding sind gemockt (externe Systeme / teure ML-Calls).
DB-Zugriff läuft ECHT gegen Postgres (via db_session-Fixture) — Grund:
dedup_node und store_node wurden gerade so umgebaut, dass ihre
Persistenz-Semantik (Idempotenz, JOIN über evaluation-Relationship,
unique-Constraint) der Kern-Regressionspunkt für M3 ist. Die gemockte
DB-Variante würde diese Semantik komplett vortäuschen.

Alles dazwischen — Job-Mapping im Search-Node, Filter-Regeln laden und
anwenden, State-Fluss zwischen fünf Nodes — läuft echt durch den
kompilierten Graphen. So fangen wir Integrationsfehler ab, die
isolierte Node-Tests übersehen würden (z.B. Feldnamens-Vertauschungen
zwischen Nodes).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.agent.graph import build_graph
from src.agent.models import JobEvaluation, Profile
from src.db.models import EvaluationORM, FilterRulesORM, JobORM
from src.db.repository import save_evaluated_job


def _seed_filter_rules(session: Session) -> None:
    """Legt die filter_rules-Singleton-Zeile für den Test-Lauf an.

    Vor Issue #14 lasen die Tests die Regeln aus data/filter_rules.yaml.
    Seit der Seed-Migration ac7556d5370e sitzen sie in der DB — die
    db_session-Fixture legt die Tabellen frisch an (kein Seed), also
    muss jeder Test, der den echten filter_node-Pfad läuft, die Zeile
    selbst schreiben.
    """
    session.add(
        FilterRulesORM(
            title_blacklist=["Senior", "Lead"],
            max_experience_years=3,
            description_blacklist=["Beratungsprojekte"],
        )
    )
    session.commit()


# --- Fixtures / Helpers ---------------------------------------------------


def _rohes_job_dict(
    id_: str,
    title: str,
    *,
    description: str = "Wir suchen jemanden für unser Team.",
) -> dict:
    """Baut ein rohes JobSpy-Dict, wie es der MCP-Server liefert.

    Feldnamen (id, job_url, is_remote, ...) sind bewusst die
    JobSpy-Originalnamen — der Search-Node mappt sie auf external_id
    usw. Diese Mapping-Logik läuft im Test echt.
    """
    return {
        "id": id_,
        "title": title,
        "company": "ACME GmbH",
        "location": "Hamburg",
        "job_url": f"https://example.com/{id_}",
        "description": description,
        "is_remote": False,
        "site": "indeed",
    }


def _build_chat_mock(evaluations: list[JobEvaluation]) -> MagicMock:
    """ChatAnthropic-Mock-Kette (identisch zu tests/test_evaluate_node.py).

    Chain-Struktur: ChatAnthropic(...) -> instanz -> with_structured_output(...) -> chain
                                                                                      -> ainvoke() -> Evaluation
    """
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=evaluations)
    chat_instance = MagicMock()
    chat_instance.with_structured_output.return_value = chain
    return MagicMock(return_value=chat_instance)


def _dummy_profile() -> Profile:
    """Minimales Test-Profil. Wird gebraucht, weil data/profile.yaml
    bewusst nicht committed ist (siehe CLAUDE.md, .env/.env.example-
    Pattern) — echtes load_profile() würde in CI fehlschlagen."""
    return Profile(
        name="Test",
        role_gesucht="Junior AI Engineer",
        erfahrung=["Bootcamp"],
        zertifikate=[],
        kernskills=["Python"],
        portfolio_projekte=["Testprojekt"],
        praeferenzen={"level": "Junior"},
    )


@pytest.fixture
def graph_session_local(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):
    """Lenkt src.agent.graph.SessionLocal auf das Test-Engine um.

    dedup_node und store_node bauen ihre eigene Session über
    SessionLocal() — ohne diesen Patch würden sie eine unabhängige
    Session gegen dieselbe DB öffnen. Für die Assertions wollen wir
    aber die db_session-Fixture-Session nutzen können, ohne Iso-Probleme.
    """
    TestSessionLocal = sessionmaker(bind=db_engine)
    monkeypatch.setattr("src.agent.graph.SessionLocal", TestSessionLocal)


# --- Der eigentliche E2E-Test ---------------------------------------------


@pytest.mark.asyncio
async def test_e2e_pipeline_search_filter_dedup_evaluate_store(
    db_session: Session,
    graph_session_local: None,
) -> None:
    """3 rohe Jobs rein (1 Senior, 2 valide) -> 2 bewertete Jobs raus.

    Beweist im Zusammenspiel:
    - Search-Node mappt rohe JobSpy-Dicts korrekt auf Job-Objekte
    - Filter-Node liest die Regeln aus der DB (Seed-Zeile hier gelegt)
      und wendet title_blacklist an (Senior fliegt raus)
    - Dedup-Node erkennt keinen bekannten Job (leere DB) -> alles geht
      weiter an Evaluate
    - Evaluate-Node ruft die gemockte Chain für jeden gefilterten Job auf
    - Store-Node persistiert die evaluated_jobs in jobs+evaluations,
      Embedding-Spalte ist befüllt
    """
    # filter_rules-Zeile für filter_node bereitstellen
    _seed_filter_rules(db_session)

    # Rohdaten des MCP-Servers simulieren — einer davon wird vom Filter
    # aussortiert (title_blacklist enthält "Senior")
    rohe_jobs = [
        _rohes_job_dict("e2e-junior-1", "Junior AI Engineer"),
        _rohes_job_dict("e2e-junior-2", "Junior Data Engineer"),
        _rohes_job_dict("e2e-senior", "Senior Data Engineer"),
    ]

    # Bewertungs-Chain: pro gefiltertem Job eine feste Bewertung.
    # Reihenfolge muss zur Iterationsreihenfolge der filtered_jobs passen
    eval_1 = JobEvaluation(
        fit_score=0.9,
        reasoning="Starker Match für Junior AI Engineer.",
        matched_skills=["Python", "LangGraph"],
        missing_skills=[],
    )
    eval_2 = JobEvaluation(
        fit_score=0.7,
        reasoning="Guter Match, andere Teil-Domäne.",
        matched_skills=["Python"],
        missing_skills=["Airflow"],
    )
    chat_mock = _build_chat_mock([eval_1, eval_2])

    # Externe Grenzen patchen — alles andere läuft echt durch.
    # load_filter_rules bewusst NICHT gemockt: die YAML ist committed,
    # damit der Test auch fängt, wenn dort etwas Kaputtes gemergt wird.
    # load_profile IST gemockt (data/profile.yaml nicht committed).
    # generate_embedding IST gemockt (kein ML-Modell in automatisierten Tests).
    with patch(
        "src.agent.graph.search_jobs_via_mcp",
        new_callable=AsyncMock,
        return_value=rohe_jobs,
    ), patch("src.agent.graph.ChatAnthropic", chat_mock), patch(
        "src.agent.graph.load_profile", return_value=_dummy_profile()
    ), patch(
        "src.agent.graph.generate_embedding", return_value=[0.0] * 384
    ):
        graph = build_graph()
        result = await graph.ainvoke(
            {
                "search_term": "Junior AI Engineer",
                "location": "Hamburg",
                "raw_jobs": [],
                "filtered_jobs": [],
                "rejected_jobs": [],
                "evaluated_jobs": [],
                "errors": [],
            }
        )

    # --- Search-Node-Ergebnis ---
    # Alle 3 rohen Dicts wurden zu Job-Objekten gemappt
    assert len(result["raw_jobs"]) == 3

    # --- Filter-Node-Ergebnis ---
    # 2 Junior-Jobs bestehen, 1 Senior-Job wird abgelehnt
    assert len(result["filtered_jobs"]) == 2
    assert len(result["rejected_jobs"]) == 1
    assert result["rejected_jobs"][0].job.external_id == "e2e-senior"
    # Die Begründung muss den Titel-Blacklist-Term nennen
    assert "Senior" in result["rejected_jobs"][0].rejection_reason

    # --- Evaluate-Node-Ergebnis ---
    # 2 gefilterte Jobs -> 2 EvaluatedJob-Objekte, in Reihenfolge
    assert len(result["evaluated_jobs"]) == 2
    assert result["evaluated_jobs"][0].job.external_id == "e2e-junior-1"
    assert result["evaluated_jobs"][0].evaluation.fit_score == 0.9
    assert result["evaluated_jobs"][1].job.external_id == "e2e-junior-2"
    assert result["evaluated_jobs"][1].evaluation.fit_score == 0.7

    # Keine Fehler im gesamten Lauf — sonst hätte irgendein Node Probleme
    assert result["errors"] == []

    # --- Store-Node-Ergebnis (DB statt JSON-Datei) ---
    # Beide Jobs sind in der jobs-Tabelle, mit befülltem embedding
    persistierte_jobs = (
        db_session.query(JobORM)
        .filter(JobORM.external_id.in_(["e2e-junior-1", "e2e-junior-2"]))
        .all()
    )
    assert len(persistierte_jobs) == 2
    for job_orm in persistierte_jobs:
        assert job_orm.embedding is not None
        assert len(job_orm.embedding) == 384

    # evaluations-Tabelle: zu jedem Job existiert genau eine Bewertung
    persistierte_ids = [j.id for j in persistierte_jobs]
    assert (
        db_session.query(EvaluationORM)
        .filter(EvaluationORM.job_id.in_(persistierte_ids))
        .count()
        == 2
    )


@pytest.mark.asyncio
async def test_e2e_dedup_holt_bekannten_job_aus_db_und_ueberspringt_llm(
    db_session: Session,
    graph_session_local: None,
) -> None:
    """Vorher gespeicherter Job wird von dedup_node erkannt und
    NICHT erneut an Evaluate/LLM geschickt.

    Konkret: 2 gefilterte Jobs, einer davon liegt schon in der DB. Der
    Chat-Mock stellt nur EINE Bewertung bereit — würde evaluate_node
    trotzdem zwei Jobs bewerten wollen, ginge der Test durch StopIteration
    kaputt. So beweisen wir den Kosten-Spar-Effekt strukturell.
    """
    from src.agent.models import EvaluatedJob, Job

    # Bekannten Job vorher in die DB legen — externe_id "e2e-known"
    bekannt = EvaluatedJob(
        job=Job(
            external_id="e2e-known",
            title="Junior AI Engineer",
            company="ACME GmbH",
            location="Hamburg",
            job_url="https://example.com/e2e-known",
            description="Wir suchen jemanden für unser Team.",
            is_remote=False,
            site="indeed",
        ),
        evaluation=JobEvaluation(
            fit_score=0.65,
            reasoning="Aus vorherigem Lauf.",
            matched_skills=["Python"],
            missing_skills=[],
        ),
    )
    save_evaluated_job(db_session, bekannt, [0.0] * 384)
    db_session.commit()

    # filter_rules-Zeile für filter_node bereitstellen
    _seed_filter_rules(db_session)

    rohe_jobs = [
        _rohes_job_dict("e2e-known", "Junior AI Engineer"),
        _rohes_job_dict("e2e-brandneu", "Junior Data Engineer"),
    ]

    # Nur EINE Bewertung im Mock — Beweis, dass evaluate nur einmal aufgerufen wird
    eval_neu = JobEvaluation(
        fit_score=0.8,
        reasoning="Neu bewertet.",
        matched_skills=["Python"],
        missing_skills=[],
    )
    chat_mock = _build_chat_mock([eval_neu])

    with patch(
        "src.agent.graph.search_jobs_via_mcp",
        new_callable=AsyncMock,
        return_value=rohe_jobs,
    ), patch("src.agent.graph.ChatAnthropic", chat_mock), patch(
        "src.agent.graph.load_profile", return_value=_dummy_profile()
    ), patch(
        "src.agent.graph.generate_embedding", return_value=[0.0] * 384
    ) as mock_emb:
        graph = build_graph()
        result = await graph.ainvoke(
            {
                "search_term": "Junior AI Engineer",
                "location": "Hamburg",
                "raw_jobs": [],
                "filtered_jobs": [],
                "rejected_jobs": [],
                "evaluated_jobs": [],
                "errors": [],
            }
        )

    assert result["errors"] == []

    # evaluated_jobs enthält BEIDE Jobs — den bekannten (aus DB) plus
    # den neu bewerteten
    ids = {ej.job.external_id for ej in result["evaluated_jobs"]}
    assert ids == {"e2e-known", "e2e-brandneu"}

    # Der bekannte Job trägt den DB-Score (0.65), nicht den Mock-Score (0.8)
    known_ej = next(ej for ej in result["evaluated_jobs"] if ej.job.external_id == "e2e-known")
    assert known_ej.evaluation.fit_score == 0.65

    # Embedding wurde NUR für den neuen Job berechnet — Kern-Ersparnis
    assert mock_emb.call_count == 1

    # DB enthält jetzt beide Jobs, jeweils genau einmal
    assert (
        db_session.query(JobORM)
        .filter(JobORM.external_id.in_(["e2e-known", "e2e-brandneu"]))
        .count()
        == 2
    )

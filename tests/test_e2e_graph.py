"""End-to-End-Test für den kompletten LangGraph-Graphen.

Dieser Test ist die automatisierte, gemockte Entsprechung von
tests/manual/full_agent_run_check.py — letzteres verifiziert mit
echten Daten (echter MCP-Server, echte Anthropic-API), dass die
Pipeline inhaltlich funktioniert; dieser Test hier verifiziert das
Zusammenspiel der Nodes deterministisch und ohne Kosten.

Mocking-Grenze bewusst eng gezogen: nur die zwei externen Systeme
werden gemockt (MCP-Client + ChatAnthropic-LLM). Alles dazwischen —
Job-Mapping im Search-Node, Filter-Regeln laden und anwenden, State-
Fluss, JSON-Serialisierung im Storage-Node — läuft echt durch den
kompilierten Graphen. So fangen wir Integrationsfehler ab, die
isolierte Node-Tests übersehen würden (z.B. Feldnamens-Vertauschungen
zwischen Nodes).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.graph import build_graph
from src.agent.models import JobEvaluation, Profile


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


# --- Der eigentliche E2E-Test ---------------------------------------------


@pytest.mark.asyncio
async def test_e2e_pipeline_search_filter_evaluate_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 rohe Jobs rein (1 Senior, 2 valide) -> 2 bewertete Jobs raus,
    Storage-Datei enthält diese 2, rejected_jobs enthält den Senior-Job.

    Beweist im Zusammenspiel:
    - Search-Node mappt rohe JobSpy-Dicts korrekt auf Job-Objekte
    - Filter-Node liest die echte data/filter_rules.yaml und wendet
      title_blacklist an (Senior fliegt raus)
    - Evaluate-Node ruft die gemockte Chain für jeden gefilterten Job auf
    - Storage-Node schreibt die evaluated_jobs als JSON nach tmp_path
    """
    # Storage-Ziel umlenken, damit der Test nicht data/results/ verschmutzt
    monkeypatch.setattr("src.agent.graph.settings.results_dir", str(tmp_path))

    # Rohdaten des MCP-Servers simulieren — einer davon wird vom Filter
    # aussortiert (title_blacklist enthält "Senior")
    rohe_jobs = [
        _rohes_job_dict("job-junior-1", "Junior AI Engineer"),
        _rohes_job_dict("job-junior-2", "Junior Data Engineer"),
        _rohes_job_dict("job-senior", "Senior Data Engineer"),
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
    # load_profile IST gemockt, weil data/profile.yaml bewusst nicht
    # committed ist (siehe _dummy_profile-Docstring).
    with patch(
        "src.agent.graph.search_jobs_via_mcp",
        new_callable=AsyncMock,
        return_value=rohe_jobs,
    ), patch("src.agent.graph.ChatAnthropic", chat_mock), patch(
        "src.agent.graph.load_profile", return_value=_dummy_profile()
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
    assert result["rejected_jobs"][0].job.external_id == "job-senior"
    # Die Begründung muss den Titel-Blacklist-Term nennen
    assert "Senior" in result["rejected_jobs"][0].rejection_reason

    # --- Evaluate-Node-Ergebnis ---
    # 2 gefilterte Jobs -> 2 EvaluatedJob-Objekte, in Reihenfolge
    assert len(result["evaluated_jobs"]) == 2
    assert result["evaluated_jobs"][0].job.external_id == "job-junior-1"
    assert result["evaluated_jobs"][0].evaluation.fit_score == 0.9
    assert result["evaluated_jobs"][1].job.external_id == "job-junior-2"
    assert result["evaluated_jobs"][1].evaluation.fit_score == 0.7

    # Keine Fehler im gesamten Lauf — sonst hätte irgendein Node Probleme
    assert result["errors"] == []

    # --- Storage-Node-Ergebnis ---
    # Genau eine Datei geschrieben, mit den 2 bewerteten Jobs
    dateien = list(tmp_path.glob("*.json"))
    assert len(dateien) == 1
    gespeichert = json.loads(dateien[0].read_text(encoding="utf-8"))
    assert len(gespeichert) == 2
    gespeicherte_ids = {eintrag["job"]["external_id"] for eintrag in gespeichert}
    assert gespeicherte_ids == {"job-junior-1", "job-junior-2"}

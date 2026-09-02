"""Integrationstests für evaluate_node() aus src/agent/graph.py.

ChatAnthropic wird KOMPLETT gemockt (kein echter API-Call).
Mock-Kette: ChatAnthropic() -> instanz -> with_structured_output(...) -> chain
                                                                          -> ainvoke() -> JobEvaluation
load_profile wird ebenfalls gepatcht, damit der Test nicht auf einer
echten data/profile.yaml hängt.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.graph import evaluate_node
from src.agent.models import EvaluatedJob, Job, JobEvaluation, Profile


def _make_job(external_id: str, *, title: str = "Junior AI Engineer") -> Job:
    """Kompakter Job-Faktor — nur external_id + title sind pro Test relevant,
    der Rest ist Dummy-Werte, damit Pydantic beim Instanziieren happy ist."""
    return Job(
        external_id=external_id,
        title=title,
        company="ACME GmbH",
        location="Hamburg",
        job_url=f"https://example.com/{external_id}",
        description="Beschreibung des Jobs, egal was hier steht.",
        is_remote=False,
        site="indeed",
    )


def _dummy_profile() -> Profile:
    """Minimales Profil — nur so viel, dass Pydantic-Pflichtfelder erfüllt sind."""
    return Profile(
        name="Test",
        role_gesucht="Junior AI Engineer",
        erfahrung=["Bootcamp"],
        zertifikate=[],
        kernskills=["Python"],
        portfolio_projekte=["Testprojekt"],
        praeferenzen={"level": "Junior"},
    )


def _base_state(filtered_jobs: list[Job]) -> dict:
    """Vollständiger AgentState-kompatibler Dict für die Node-Aufrufe."""
    return {
        "search_term": "AI Engineer",
        "location": "Hamburg",
        "raw_jobs": [],
        "filtered_jobs": filtered_jobs,
        "rejected_jobs": [],
        "evaluated_jobs": [],
        "errors": [],
    }


def _build_chat_mock(evaluations_or_exceptions: list[object]) -> MagicMock:
    """Baut den ChatAnthropic-Mock inkl. with_structured_output-Chain.

    Parameter:
        evaluations_or_exceptions: pro erwartetem Job entweder eine
            JobEvaluation-Instanz (erfolgreicher Call) oder eine Exception
            (die vom Mock beim entsprechenden Aufruf geworfen wird).

    Struktur der Kette:
        ChatAnthropic(...)                         <- callable Klasse
            .with_structured_output(JobEvaluation) <- gibt chain zurück
                .ainvoke([...])                    <- gibt Evaluation zurück
    """
    # ainvoke = AsyncMock mit side_effect: pro Aufruf nächster Wert der Liste;
    # ist der Wert eine Exception, wirft AsyncMock diese automatisch
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=evaluations_or_exceptions)

    chat_instance = MagicMock()
    chat_instance.with_structured_output.return_value = chain

    # Die Klasse ChatAnthropic wird instanziiert -> gibt chat_instance zurück
    chat_class = MagicMock(return_value=chat_instance)
    return chat_class


# --- Tests ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_node_bewertet_alle_gefilterten_jobs() -> None:
    """2 Jobs rein -> 2 EvaluatedJob-Objekte mit den gemockten Bewertungen.

    Prüft auch, dass die Zuordnung Job-zu-Evaluation stimmt (Reihenfolge
    darf nicht vertauscht werden — sequenzielle Iteration).
    """
    jobs = [
        _make_job("job-1", title="Junior AI Engineer"),
        _make_job("job-2", title="Junior Data Engineer"),
    ]
    eval_1 = JobEvaluation(
        fit_score=0.9,
        reasoning="Starker Match.",
        matched_skills=["Python", "LangGraph"],
        missing_skills=[],
    )
    eval_2 = JobEvaluation(
        fit_score=0.6,
        reasoning="Teilweiser Match.",
        matched_skills=["Python"],
        missing_skills=["Airflow"],
    )
    chat_mock = _build_chat_mock([eval_1, eval_2])

    # Beide externen Abhängigkeiten am Import-Ort in graph.py patchen
    with patch("src.agent.graph.ChatAnthropic", chat_mock), patch(
        "src.agent.graph.load_profile", return_value=_dummy_profile()
    ):
        # Leeres config-Dict reicht — LangGraph würde in Produktion den
        # echten RunnableConfig injizieren, für den Node-Test spielt sein
        # Inhalt keine Rolle.
        result = await evaluate_node(_base_state(jobs), {})

    evaluated: list[EvaluatedJob] = result["evaluated_jobs"]
    assert len(evaluated) == 2
    # Reihenfolge = Reihenfolge in filtered_jobs, Evaluation gehört zum Job
    assert evaluated[0].job.external_id == "job-1"
    assert evaluated[0].evaluation.fit_score == 0.9
    assert evaluated[1].job.external_id == "job-2"
    assert evaluated[1].evaluation.fit_score == 0.6
    # Keine Fehler -> errors-Key wird gar nicht zurückgegeben
    assert "errors" not in result


@pytest.mark.asyncio
async def test_evaluate_node_leere_liste_macht_keinen_api_call() -> None:
    """Ohne gefilterte Jobs darf der Node keinen einzigen API-Call machen —
    sonst würde ein leerer Suchlauf trotzdem Kosten produzieren.

    Rückgabe ist ein LEERES Dict, kein {"evaluated_jobs": []}. Grund:
    LangGraph überschreibt im State exakt die Keys, die im Rückgabe-Dict
    stehen. dedup_node kann evaluated_jobs bereits mit Dedup-Treffern
    vorbefüllt haben — würde evaluate_node hier {"evaluated_jobs": []}
    zurückgeben, würden diese Einträge gelöscht. Ein leeres Dict lässt
    den State unangetastet und ist deshalb die korrekte "nichts zu tun"-
    Signalisierung.
    """
    chat_mock = _build_chat_mock([])  # side_effect leer, würde aber sofort scheitern

    with patch("src.agent.graph.ChatAnthropic", chat_mock), patch(
        "src.agent.graph.load_profile", return_value=_dummy_profile()
    ):
        result = await evaluate_node(_base_state([]), {})

    # Leer, damit dedup_node-Einträge im State erhalten bleiben (siehe Docstring)
    assert result == {}
    # Die Kernaussage: ChatAnthropic wurde NIE instanziiert
    chat_mock.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_node_ueberspringt_kaputter_job_und_verarbeitet_rest() -> None:
    """Einer von zwei API-Calls wirft eine Exception:
    - der andere Job wird trotzdem bewertet (keine Alles-oder-Nichts-Logik)
    - der Fehler landet in errors, mit external_id im Text
    """
    jobs = [
        _make_job("job-crash"),
        _make_job("job-ok"),
    ]
    # side_effect: erster Call -> Exception, zweiter Call -> gültige Evaluation
    eval_ok = JobEvaluation(
        fit_score=0.8,
        reasoning="OK.",
        matched_skills=["Python"],
        missing_skills=[],
    )
    chat_mock = _build_chat_mock([RuntimeError("API kaputt"), eval_ok])

    with patch("src.agent.graph.ChatAnthropic", chat_mock), patch(
        "src.agent.graph.load_profile", return_value=_dummy_profile()
    ):
        result = await evaluate_node(_base_state(jobs), {})

    evaluated: list[EvaluatedJob] = result["evaluated_jobs"]
    # Nur der zweite Job kommt durch
    assert len(evaluated) == 1
    assert evaluated[0].job.external_id == "job-ok"

    # Fehler enthält die external_id des übersprungenen Jobs
    assert "errors" in result
    assert len(result["errors"]) == 1
    assert "job-crash" in result["errors"][0]

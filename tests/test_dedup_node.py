"""Unit-Tests für dedup_node() aus src/agent/graph.py.

Repository- und Session-Funktionen werden am Import-Ort in
src.agent.graph gepatcht — keine echte DB-Verbindung. Die Node-Logik
(Splitting bekannt/unbekannt, State-Rückgabe, Kurzschluss bei leerer
Liste) soll isoliert von Persistenz-Details testbar sein.

Der reale DB-Pfad ist über test_repository.py und test_store_node.py
abgedeckt — dort mit echter Postgres-Verbindung.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.agent.graph import dedup_node
from src.agent.models import EvaluatedJob, Job, JobEvaluation


def _make_job(external_id: str) -> Job:
    """Kompakter Job-Faktor — nur external_id ist pro Test relevant."""
    return Job(
        external_id=external_id,
        title="Junior AI Engineer",
        company="ACME GmbH",
        location="Hamburg",
        job_url=f"https://example.com/{external_id}",
        description="Beschreibung.",
        is_remote=False,
        site="indeed",
    )


def _make_evaluated_job(external_id: str, fit_score: float = 0.8) -> EvaluatedJob:
    """Wird als Rückgabewert von load_evaluated_job simuliert — repräsentiert
    einen Job, der schon in der DB liegt und samt Bewertung geladen wird."""
    return EvaluatedJob(
        job=_make_job(external_id),
        evaluation=JobEvaluation(
            fit_score=fit_score,
            reasoning="Aus DB rekonstruiert.",
            matched_skills=["Python"],
            missing_skills=[],
        ),
    )


def _base_state(filtered_jobs: list[Job], evaluated_jobs: list[EvaluatedJob]) -> dict:
    """AgentState-kompatibles Dict für die Node-Aufrufe."""
    return {
        "search_term": "AI Engineer",
        "location": "Hamburg",
        "raw_jobs": [],
        "filtered_jobs": filtered_jobs,
        "rejected_jobs": [],
        "evaluated_jobs": evaluated_jobs,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_dedup_node_trennt_bekannte_von_unbekannten() -> None:
    """3 filtered_jobs, davon 1 bekannt:
    - filtered_jobs danach nur noch die 2 unbekannten
    - evaluated_jobs um den bekannten (aus DB rekonstruierten) gewachsen
    """
    jobs = [
        _make_job("neu-1"),
        _make_job("bekannt-1"),
        _make_job("neu-2"),
    ]
    aus_db = _make_evaluated_job("bekannt-1", fit_score=0.9)

    # SessionLocal gemockt: () -> mock_session; close() reicht als No-op
    mock_session = MagicMock()
    with patch("src.agent.graph.SessionLocal", return_value=mock_session), patch(
        "src.agent.graph.get_known_external_ids", return_value={"bekannt-1"}
    ), patch("src.agent.graph.load_evaluated_job", return_value=aus_db):
        result = await dedup_node(_base_state(jobs, evaluated_jobs=[]))

    # Nur die unbekannten bleiben zurück, ihre Reihenfolge muss erhalten sein
    assert [j.external_id for j in result["filtered_jobs"]] == ["neu-1", "neu-2"]
    # Der bekannte Job wurde aus der DB in evaluated_jobs überführt
    assert len(result["evaluated_jobs"]) == 1
    assert result["evaluated_jobs"][0].job.external_id == "bekannt-1"
    assert result["evaluated_jobs"][0].evaluation.fit_score == 0.9
    # Session muss geschlossen worden sein — sonst leaken Connections
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_dedup_node_keine_bekannten_laesst_alles_unveraendert() -> None:
    """Wenn nichts in der DB ist, gehen alle Jobs unverändert weiter zum
    evaluate_node — evaluated_jobs bleibt leer, filtered_jobs identisch."""
    jobs = [_make_job("neu-1"), _make_job("neu-2")]

    mock_session = MagicMock()
    with patch("src.agent.graph.SessionLocal", return_value=mock_session), patch(
        "src.agent.graph.get_known_external_ids", return_value=set()
    ), patch("src.agent.graph.load_evaluated_job") as mock_load:
        result = await dedup_node(_base_state(jobs, evaluated_jobs=[]))

    assert [j.external_id for j in result["filtered_jobs"]] == ["neu-1", "neu-2"]
    assert result["evaluated_jobs"] == []
    # load_evaluated_job darf für keinen einzigen Job aufgerufen worden
    # sein — sonst wäre die "bekannt?"-Prüfung defekt
    mock_load.assert_not_called()


@pytest.mark.asyncio
async def test_dedup_node_alle_bekannt_leert_filtered_jobs() -> None:
    """Wenn ALLE gefilterten Jobs bereits in der DB sind:
    - filtered_jobs wird leer (evaluate_node bekommt nichts mehr)
    - alle drei landen in evaluated_jobs
    """
    jobs = [_make_job("bekannt-a"), _make_job("bekannt-b"), _make_job("bekannt-c")]

    # load_evaluated_job liefert für jeden Aufruf den passenden Mock
    def _load_stub(_session, ext_id):
        return _make_evaluated_job(ext_id, fit_score=0.5)

    mock_session = MagicMock()
    with patch("src.agent.graph.SessionLocal", return_value=mock_session), patch(
        "src.agent.graph.get_known_external_ids",
        return_value={"bekannt-a", "bekannt-b", "bekannt-c"},
    ), patch("src.agent.graph.load_evaluated_job", side_effect=_load_stub):
        result = await dedup_node(_base_state(jobs, evaluated_jobs=[]))

    assert result["filtered_jobs"] == []
    assert {ej.job.external_id for ej in result["evaluated_jobs"]} == {
        "bekannt-a",
        "bekannt-b",
        "bekannt-c",
    }


@pytest.mark.asyncio
async def test_dedup_node_leere_liste_baut_keine_session_auf() -> None:
    """Ohne filtered_jobs: kein SessionLocal(), kein DB-Query, leere Rückgabe.

    Kurzschluss-Optimierung — sonst würden Nulltreffer-Läufe unnötig
    eine DB-Verbindung öffnen.
    """
    with patch("src.agent.graph.SessionLocal") as mock_session_local:
        result = await dedup_node(_base_state([], evaluated_jobs=[]))

    assert result == {}
    mock_session_local.assert_not_called()

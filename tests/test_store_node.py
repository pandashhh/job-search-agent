"""Unit-Tests für store_node() aus src/agent/graph.py.

monkeypatch lenkt settings.results_dir auf tmp_path um — so schreibt der
Test nicht in das echte data/results/, und pytest räumt tmp_path danach
automatisch auf.
"""

import json
from pathlib import Path

import pytest

from src.agent.graph import store_node
from src.agent.models import EvaluatedJob, Job, JobEvaluation


def _make_evaluated_job(external_id: str, fit_score: float) -> EvaluatedJob:
    """Fabrik für EvaluatedJob mit sinnvollen Defaults.

    Nur external_id und fit_score sind pro Test relevant — der Rest
    sind Dummy-Werte, damit Pydantic beim Instanziieren durchgeht.
    """
    return EvaluatedJob(
        job=Job(
            external_id=external_id,
            title="Junior AI Engineer",
            company="ACME GmbH",
            location="Hamburg",
            job_url=f"https://example.com/{external_id}",
            description="Beschreibung.",
            is_remote=False,
            site="indeed",
        ),
        evaluation=JobEvaluation(
            fit_score=fit_score,
            reasoning="Testbegründung.",
            matched_skills=["Python"],
            missing_skills=[],
        ),
    )


def _base_state(evaluated_jobs: list[EvaluatedJob]) -> dict:
    """AgentState-kompatibler Dict mit den Pflichtfeldern."""
    return {
        "search_term": "AI Engineer",
        "location": "Hamburg",
        "raw_jobs": [],
        "filtered_jobs": [],
        "rejected_jobs": [],
        "evaluated_jobs": evaluated_jobs,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_store_node_schreibt_evaluated_jobs_als_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2 EvaluatedJobs rein -> genau eine JSON-Datei mit beiden Jobs raus.

    Prüft die Serialisierung end-to-end: JSON parsen, verschachtelte
    Felder (job.external_id, evaluation.fit_score) auf Richtigkeit
    kontrollieren.
    """
    # settings.results_dir auf tmp_path umlenken — greift, weil store_node
    # zur Laufzeit auf settings.results_dir zugreift, nicht auf einen
    # kopierten Wert
    monkeypatch.setattr("src.agent.graph.settings.results_dir", str(tmp_path))

    jobs = [
        _make_evaluated_job("job-1", 0.9),
        _make_evaluated_job("job-2", 0.6),
    ]
    result = await store_node(_base_state(jobs))

    # Store hat keinen State-Return-Wert — bei Erfolg leeres Dict
    assert result == {}

    # Es darf genau eine Datei entstanden sein
    dateien = list(tmp_path.glob("*.json"))
    assert len(dateien) == 1

    # Dateiname folgt dem Format YYYYMMDD_HHMMSS.json (8 Ziffern + _ + 6 Ziffern)
    assert dateien[0].name[:8].isdigit()
    assert dateien[0].name[8] == "_"
    assert dateien[0].name[9:15].isdigit()

    # Inhalt: die 2 Jobs mit richtigen IDs und Scores
    daten = json.loads(dateien[0].read_text(encoding="utf-8"))
    assert len(daten) == 2
    assert daten[0]["job"]["external_id"] == "job-1"
    assert daten[0]["evaluation"]["fit_score"] == 0.9
    assert daten[1]["job"]["external_id"] == "job-2"
    assert daten[1]["evaluation"]["fit_score"] == 0.6


@pytest.mark.asyncio
async def test_store_node_schreibt_datei_auch_bei_leerer_liste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nulltreffer-Läufe sollen genauso nachvollziehbar sein wie
    erfolgreiche — bewusst KEIN Skip bei leerer Liste."""
    monkeypatch.setattr("src.agent.graph.settings.results_dir", str(tmp_path))

    result = await store_node(_base_state([]))

    assert result == {}
    dateien = list(tmp_path.glob("*.json"))
    assert len(dateien) == 1
    # Inhalt ist ein leeres JSON-Array — das ist der Marker "Lauf lief,
    # aber es gab nichts zu speichern"
    assert json.loads(dateien[0].read_text(encoding="utf-8")) == []

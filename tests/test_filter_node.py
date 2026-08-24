"""Integrationstest für filter_node() aus src/agent/graph.py.

load_filter_rules wird gepatcht, damit der Test nicht auf einer echten
DB-Zeile hängt — sonst würde eine Regeländerung in der Seed-Migration
diesen Test still zerstören. Zusätzlich wird SessionLocal gepatcht, damit
der Node keinen Verbindungsversuch startet (die Session wird ans gemockte
load_filter_rules weitergereicht und danach geschlossen, mehr nicht).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.agent.graph import filter_node
from src.agent.models import FilterRules, Job, RejectedJob


def _make_job(
    external_id: str,
    *,
    title: str = "Junior AI Engineer",
    description: str = "Wir suchen dich für unser Team.",
) -> Job:
    """Job-Fabrik mit sinnvollen Defaults — nur die Felder, die der
    Filter tatsächlich prüft (title, description), sind pro Test variabel."""
    return Job(
        external_id=external_id,
        title=title,
        company="ACME GmbH",
        location="Hamburg",
        job_url=f"https://example.com/{external_id}",
        description=description,
        is_remote=False,
        site="indeed",
    )


@pytest.mark.asyncio
async def test_filter_node_teilt_gemischte_liste_korrekt_auf() -> None:
    """4 Jobs rein, 2 durch (Junior/Junior), 2 abgelehnt (Senior/10 Jahre).

    Prüft auch, dass die rejection_reason-Werte sinnvoll gesetzt sind —
    ein Test, der nur die Anzahl prüfen würde, könnte Vertauschungen der
    Begründungen nicht erkennen.
    """
    jobs = [
        _make_job("valid-1", title="Junior Data Engineer"),
        _make_job("valid-2", title="Junior AI Engineer"),
        _make_job("rej-senior", title="Senior Data Engineer"),
        _make_job(
            "rej-experience",
            title="Junior AI Engineer",
            description="10 Jahre Erfahrung mit Machine Learning erforderlich.",
        ),
    ]

    # Testregeln zusammenbauen — bewusst nicht die YAML lesen
    fake_rules = FilterRules(
        title_blacklist=["Senior"],
        max_experience_years=3,
        description_blacklist=["Beratungsprojekte"],
    )

    # Patch am Import-Ort: filter_node greift auf den Namen zu, den es in
    # graph.py importiert hat — nicht auf src.agent.filters.load_filter_rules.
    # SessionLocal auf MagicMock, damit der Node keinen Verbindungsversuch
    # startet (der Session-Wert wird ans gemockte load_filter_rules
    # weitergereicht und danach geschlossen).
    with patch(
        "src.agent.graph.SessionLocal", return_value=MagicMock()
    ), patch(
        "src.agent.graph.load_filter_rules",
        return_value=fake_rules,
    ):
        state = {
            "search_term": "AI Engineer",
            "location": "Hamburg",
            "raw_jobs": jobs,
            "filtered_jobs": [],
            "rejected_jobs": [],
            "evaluated_jobs": [],
            "errors": [],
        }
        result = await filter_node(state)

    # Struktur: filter_node liefert genau diese zwei Keys
    assert set(result.keys()) == {"filtered_jobs", "rejected_jobs"}

    # Die zwei Junior-Jobs kommen durch
    filtered_ids = {j.external_id for j in result["filtered_jobs"]}
    assert filtered_ids == {"valid-1", "valid-2"}

    # Die zwei problematischen Jobs sind abgelehnt und tragen sinnvolle Gründe
    rejected: list[RejectedJob] = result["rejected_jobs"]
    assert len(rejected) == 2
    by_id = {r.job.external_id: r.rejection_reason for r in rejected}
    # Titel-Blacklist muss den auslösenden Term nennen
    assert by_id["rej-senior"] == "title_blacklist: Senior"
    # Erfahrungs-Check muss die gefundene Zahl in der Begründung haben
    assert "10" in by_id["rej-experience"]
    assert "experience" in by_id["rej-experience"]


@pytest.mark.asyncio
async def test_filter_node_leere_raw_jobs_liefert_leere_listen() -> None:
    """Ohne Suchergebnisse darf der Node keinen Fehler werfen —
    beide Listen bleiben leer, kein Crash."""
    fake_rules = FilterRules(
        title_blacklist=["Senior"],
        max_experience_years=3,
        description_blacklist=[],
    )

    with patch(
        "src.agent.graph.SessionLocal", return_value=MagicMock()
    ), patch(
        "src.agent.graph.load_filter_rules",
        return_value=fake_rules,
    ):
        state = {
            "search_term": "AI Engineer",
            "location": "Hamburg",
            "raw_jobs": [],
            "filtered_jobs": [],
            "rejected_jobs": [],
            "evaluated_jobs": [],
            "errors": [],
        }
        result = await filter_node(state)

    assert result == {"filtered_jobs": [], "rejected_jobs": []}

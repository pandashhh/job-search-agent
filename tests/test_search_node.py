"""
Unit-Tests für search_node() in src/agent/graph.py.

search_jobs_via_mcp wird durchgehend gemockt — keine echten Netzwerk-Calls
und kein laufender MCP-Server nötig.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent.graph import search_node

PATCH_TARGET = "src.agent.graph.search_jobs_via_mcp"

# Dummy-State mit allen Pflichtfeldern — nur search_term/location und errors
# sind für search_node relevant, der Rest bleibt unverändert
BASE_STATE = {
    "search_term": "Junior AI Engineer",
    "location": "Hamburg",
    "raw_jobs": [],
    "filtered_jobs": [],
    "rejected_jobs": [],
    "evaluated_jobs": [],
    "errors": [],
}


def _raw_job(job_id: str = "job-1") -> dict:
    """Minimales valides Job-Dict so wie JobSpy es liefert.

    Wichtig: das Feld heißt hier "id" (JobSpy-Konvention), nicht "external_id"
    (unser Modell) — das explizite Mapping in search_node() muss das auflösen.
    """
    return {
        "id": job_id,
        "title": "Junior AI Engineer",
        "company": "TechCorp GmbH",
        "location": "Hamburg, Germany",
        "job_url": f"https://indeed.com/job/{job_id}",
        "description": "Spannende Stelle im AI-Bereich.",
        "is_remote": False,
        "site": "indeed",
        # Optionale Felder bewusst gesetzt, um Mapping vollständig zu testen
        "job_type": "fulltime",
        "date_posted": "2024-01-15T00:00:00.000",
        "min_amount": 50000.0,
        "max_amount": 70000.0,
    }


@pytest.mark.asyncio
async def test_search_node_mappt_valide_jobs() -> None:
    """Normalfall: 2 valide Job-Dicts werden korrekt auf Job-Objekte gemappt.

    Prüft insbesondere das id → external_id-Mapping, da das der einzige
    nicht-triviale Unterschied zwischen JobSpy-Output und unserem Modell ist.
    """
    with patch(PATCH_TARGET, new_callable=AsyncMock) as mock_client:
        mock_client.return_value = [_raw_job("job-1"), _raw_job("job-2")]
        result = await search_node(BASE_STATE)

    assert "raw_jobs" in result
    assert len(result["raw_jobs"]) == 2

    # Prüfe id → external_id-Mapping am ersten Job
    assert result["raw_jobs"][0].external_id == "job-1"
    assert result["raw_jobs"][1].external_id == "job-2"

    # Keine Fehler bei validen Daten
    assert "errors" not in result or result.get("errors") == []


@pytest.mark.asyncio
async def test_search_node_mit_leerer_liste() -> None:
    """Grenzfall: keine Jobs gefunden — raw_jobs soll leere Liste sein."""
    with patch(PATCH_TARGET, new_callable=AsyncMock) as mock_client:
        mock_client.return_value = []
        result = await search_node(BASE_STATE)

    assert result["raw_jobs"] == []
    assert "errors" not in result or result.get("errors") == []


@pytest.mark.asyncio
async def test_search_node_bei_exception_schreibt_fehler_in_errors() -> None:
    """Fehlerfall: MCP-Client wirft RuntimeError (Server nicht erreichbar).

    raw_jobs darf NICHT im Rückgabe-Dict auftauchen — LangGraph lässt dann
    den bestehenden State-Wert unverändert. Der Fehler landet in errors.
    """
    with patch(PATCH_TARGET, new_callable=AsyncMock) as mock_client:
        mock_client.side_effect = RuntimeError("Verbindung fehlgeschlagen")
        result = await search_node(BASE_STATE)

    # raw_jobs nicht im Rückgabe-Dict, damit LangGraph den State nicht überschreibt
    assert "raw_jobs" not in result
    assert len(result["errors"]) == 1
    assert "Search-Node" in result["errors"][0]
    assert "Verbindung fehlgeschlagen" in result["errors"][0]


@pytest.mark.asyncio
async def test_search_node_ueberspringt_kaputter_job_und_verarbeitet_rest() -> None:
    """Teilausfall: 1 valides Dict + 1 Dict ohne Pflichtfeld "title".

    Der kaputte Job wird übersprungen, der valide Job landet in raw_jobs.
    Ein Fehler-Eintrag für den übersprungenen Job wird in errors gesammelt.
    """
    kaputter_job = _raw_job("job-broken")
    del kaputter_job["title"]  # Pflichtfeld entfernen -> KeyError beim Dict-Zugriff (wird von search_node abgefangen)

    with patch(PATCH_TARGET, new_callable=AsyncMock) as mock_client:
        mock_client.return_value = [_raw_job("job-ok"), kaputter_job]
        result = await search_node(BASE_STATE)

    assert len(result["raw_jobs"]) == 1
    assert result["raw_jobs"][0].external_id == "job-ok"

    # Fehler für den übersprungenen Job muss in errors landen
    assert len(result["errors"]) == 1
    assert "job-broken" in result["errors"][0]

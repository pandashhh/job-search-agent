"""
Unit-Tests für mcp_servers/jobspy_server/server.py.

scrape_jobs() wird durchgehend gemockt — keine echten Netzwerk-Calls.
search_jobs() selbst ist synchron (FastMCP macht daraus intern einen Tool-Handler),
daher reichen normale pytest-Funktionen ohne pytest-asyncio.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from mcp_servers.jobspy_server.server import search_jobs

# Patch-Pfad: muss auf das Modul zeigen, das scrape_jobs *importiert hat*,
# nicht auf das Original-Modul. Nur so ersetzt der Mock die richtige Referenz.
PATCH_TARGET = "mcp_servers.jobspy_server.server.scrape_jobs"


def _beispiel_dataframe() -> pd.DataFrame:
    """Hilfsfunktion: Minimal-DataFrame mit zwei Dummy-Jobs."""
    return pd.DataFrame(
        [
            {
                "title": "Junior AI Engineer",
                "company": "TechCorp GmbH",
                "location": "Hamburg",
                # date_posted als Python date-Objekt — genau so liefert JobSpy es zurück.
                # Kritischer Testfall: JSON kennt keine nativen date-Objekte, nur Strings.
                # pandas to_json() mit date_format="iso" muss das in "2024-01-15" umwandeln,
                # sonst würde json.loads() beim Aufrufer mit einem TypeError crashen.
                "date_posted": date(2024, 1, 15),
            },
            {
                "title": "Machine Learning Engineer",
                "company": "AI Startup AG",
                "location": "Hamburg",
                "date_posted": date(2024, 1, 10),
            },
        ]
    )


def test_search_jobs_gibt_valides_json_mit_iso_datum_zurueck() -> None:
    """
    Normalfall: scrape_jobs() liefert ein DataFrame mit 2 Jobs.

    Prüft drei Dinge:
    1. Rückgabewert ist ein gültiger JSON-String (kein Crash bei json.loads).
    2. Die Liste enthält genau 2 Elemente.
    3. date_posted ist ein ISO-String — nicht ein dict/Objekt oder Python-date.
       Das ist der kritische Punkt: pandas to_json() mit date_format="iso"
       serialisiert date-Objekte als "YYYY-MM-DD"-Strings. Würde dieser
       Schritt fehlen, würde json.loads() scheitern oder das Datum als
       Millisekunden-Timestamp ankommen.
    """
    with patch(PATCH_TARGET, return_value=_beispiel_dataframe()) as mock_scrape:
        result = search_jobs(
            search_term="Junior AI Engineer",
            location="Hamburg",
            site_names=["indeed"],
            results_wanted=2,
        )

        # scrape_jobs wurde mit den erwarteten Parametern aufgerufen
        mock_scrape.assert_called_once_with(
            site_name=["indeed"],
            search_term="Junior AI Engineer",
            location="Hamburg",
            results_wanted=2,
            job_type=None,
            is_remote=False,
            country_indeed="Germany",
        )

    # JSON muss parsebar sein — kein TypeError oder JSONDecodeError
    jobs = json.loads(result)

    assert len(jobs) == 2

    # date_posted muss ein ISO-String sein, kein int (Timestamp) oder dict
    for job in jobs:
        assert isinstance(job["date_posted"], str), (
            f"date_posted sollte ein ISO-String sein, ist aber: {type(job['date_posted'])}"
        )
        # pandas to_json(date_format="iso") serialisiert date-Objekte als
        # ISO-Datetime-String mit Nullzeit: "2024-01-15T00:00:00.000".
        # Prüfung: beginnt mit YYYY-MM-DD (Datumsteil korrekt).
        assert job["date_posted"][:4].isdigit()
        assert job["date_posted"][4] == "-"
        assert job["date_posted"][7] == "-"


def test_search_jobs_mit_leerem_dataframe_gibt_leeres_json_array_zurueck() -> None:
    """
    Grenzfall: scrape_jobs() findet keine Jobs (leeres DataFrame).
    search_jobs() soll "[]" zurückgeben, nicht crashen oder None liefern.
    """
    with patch(PATCH_TARGET, return_value=pd.DataFrame()):
        result = search_jobs(
            search_term="Nicht-existierender Job",
            location="Hamburg",
        )

    assert result == "[]"


def test_search_jobs_mit_none_gibt_leeres_json_array_zurueck() -> None:
    """
    Defensiver Grenzfall: scrape_jobs() gibt None zurück (undokumentiertes
    Verhalten bei manchen Fehlern in python-jobspy).
    search_jobs() soll auch hier "[]" liefern statt mit AttributeError zu crashen.
    """
    with patch(PATCH_TARGET, return_value=None):
        result = search_jobs(
            search_term="Junior AI Engineer",
            location="Hamburg",
        )

    assert result == "[]"

"""Unit-Tests für die Filter-Check-Funktionen in src/agent/filters.py.

Jede Check-Funktion wird isoliert getestet (Treffer + Kein-Treffer),
plus zwei Sonderfälle: der bewusst simple Range-Match ("3-5 Jahre" -> 5)
und das Laden einer YAML-Datei über tmp_path.
"""

import textwrap
from pathlib import Path

from src.agent.filters import (
    check_description_blacklist,
    check_experience,
    check_title_blacklist,
    load_filter_rules,
)
from src.agent.models import FilterRules, Job


def _make_job(
    *,
    title: str = "Junior AI Engineer",
    description: str = "Wir suchen dich für unser Team.",
) -> Job:
    """Kleiner Job-Fabrik-Helper mit sinnvollen Defaults.

    Nur title und description sind für die Filter-Tests relevant —
    alle anderen Pflichtfelder bekommen Dummy-Werte, damit Pydantic
    beim Instanziieren nicht meckert.
    """
    return Job(
        external_id="test-1",
        title=title,
        company="ACME GmbH",
        location="Hamburg",
        job_url="https://example.com/1",
        description=description,
        is_remote=False,
        site="indeed",
    )


# Feste Regeln für die Check-Tests — halten die Tests unabhängig von der
# echten YAML-Datei (die kann sich ändern, ohne die Test-Semantik zu brechen)
_RULES = FilterRules(
    title_blacklist=["Senior", "Lead", "Werkstudent"],
    max_experience_years=3,
    description_blacklist=["Beratungsprojekte"],
)


# --- check_title_blacklist -------------------------------------------------


def test_check_title_blacklist_findet_treffer_case_insensitive() -> None:
    """'senior' im Titel matched trotz Kleinschreibung gegen 'Senior'."""
    job = _make_job(title="senior data engineer")
    result = check_title_blacklist(job, _RULES)
    # Begründung enthält den Original-Term aus der Regel, nicht die
    # Lower-Variante — bessere Lesbarkeit im Log
    assert result == "title_blacklist: Senior"


def test_check_title_blacklist_ohne_treffer_gibt_none() -> None:
    """Ein sauberer Junior-Titel darf nicht ausgeschieden werden."""
    job = _make_job(title="Junior Machine Learning Engineer")
    assert check_title_blacklist(job, _RULES) is None


# --- check_experience ------------------------------------------------------


def test_check_experience_lehnt_hoehere_zahl_ab() -> None:
    """5 Jahre > max 3 -> Ablehnung mit erklärender Begründung."""
    job = _make_job(description="Wir erwarten 5 Jahre Erfahrung mit Python.")
    result = check_experience(job, _RULES)
    assert result is not None
    # Die höchste gefundene Zahl muss in der Begründung auftauchen
    assert "5" in result


def test_check_experience_akzeptiert_niedrige_zahl() -> None:
    """2 Jahre <= max 3 -> None (Job besteht)."""
    job = _make_job(description="Mindestens 2 Jahre Berufserfahrung.")
    assert check_experience(job, _RULES) is None


def test_check_experience_range_matched_nur_die_obere_zahl() -> None:
    """Bewusst simple Regex: 'Wir bieten 3-5 Jahre Erfahrung' -> die 5
    wird gematched, nicht die 3 oder ein Range-Objekt.

    Dieser Test dokumentiert das Verhalten explizit, damit klar ist:
    das ist kein versteckter Bug, sondern beabsichtigte Einfachheit für
    den ersten Wurf. Wenn Ranges später sauber unterstützt werden sollen,
    ist es hier klar erkennbar.
    """
    job = _make_job(description="Wir wünschen uns 3-5 Jahre Erfahrung.")
    result = check_experience(job, _RULES)
    # 5 > max=3, also Ablehnung — und 5 muss in der Begründung stehen
    assert result is not None
    assert "5" in result


def test_check_experience_findet_hoechste_bei_mehreren_treffern() -> None:
    """Zwei Angaben im Text: die HÖHERE zählt (worst case), nicht die erste."""
    job = _make_job(description="3 Jahre Python, 7 Jahre Cloud-Erfahrung.")
    result = check_experience(job, _RULES)
    assert result is not None
    # Nicht "3" — Test würde bei erster-Treffer-Logik fälschlich mit "3" durchgehen
    assert "7" in result


# --- check_description_blacklist ------------------------------------------


def test_check_description_blacklist_findet_treffer() -> None:
    """'Beratungsprojekte' in der Beschreibung -> Ablehnung."""
    job = _make_job(description="Du arbeitest in Beratungsprojekten für Kunden.")
    result = check_description_blacklist(job, _RULES)
    assert result == "description_blacklist: Beratungsprojekte"


def test_check_description_blacklist_ohne_treffer_gibt_none() -> None:
    """Neutrale Produkt-Beschreibung passiert den Filter."""
    job = _make_job(description="Du entwickelst unser internes Produkt weiter.")
    assert check_description_blacklist(job, _RULES) is None


# --- load_filter_rules ----------------------------------------------------


def test_load_filter_rules_liest_yaml_und_validiert(tmp_path: Path) -> None:
    """Schreibt eine temporäre YAML, lädt sie, prüft Werte + Typ.

    tmp_path ist eine pytest-Standard-Fixture, die pro Test ein
    frisches Temp-Verzeichnis liefert und danach aufräumt — kein Reste-
    Risiko im echten data/-Ordner.
    """
    # textwrap.dedent entfernt die Einrückung, YAML wäre sonst kaputt
    yaml_content = textwrap.dedent(
        """
        title_blacklist:
          - Senior
          - Principal
        max_experience_years: 4
        description_blacklist:
          - Reisebereitschaft
        """
    )
    yaml_file = tmp_path / "filter_rules.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    rules = load_filter_rules(str(yaml_file))

    assert isinstance(rules, FilterRules)
    assert rules.title_blacklist == ["Senior", "Principal"]
    assert rules.max_experience_years == 4
    assert rules.description_blacklist == ["Reisebereitschaft"]

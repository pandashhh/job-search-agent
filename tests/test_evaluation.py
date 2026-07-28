"""Unit-Tests für load_profile() und build_system_prompt().

Beide Funktionen sind reine Datenoperationen (kein LLM-Call), lassen
sich daher komplett ohne Mocking testen.
"""

import textwrap
from pathlib import Path

from src.agent.evaluation import build_system_prompt, load_profile
from src.agent.models import Profile


# --- load_profile ---------------------------------------------------------


def test_load_profile_liest_yaml_und_validiert(tmp_path: Path) -> None:
    """Schreibt eine temporäre profile.yaml und lädt sie über load_profile.

    Deckt die Standardfelder ab — insbesondere praeferenzen als dict,
    weil das der einzige nicht-list-Typ im Modell ist.
    """
    yaml_content = textwrap.dedent(
        """
        name: "Test Kandidat"
        role_gesucht: "Junior AI Engineer"
        erfahrung:
          - "B.Sc. Informatik"
          - "6 Monate Bootcamp"
        zertifikate:
          - "Anthropic Claude API"
        kernskills:
          - "Python"
          - "LangGraph"
        portfolio_projekte:
          - "RAG-System"
        praeferenzen:
          level: "Junior"
          standort: "Hamburg oder Remote"
        """
    )
    yaml_file = tmp_path / "profile.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    profile = load_profile(str(yaml_file))

    assert isinstance(profile, Profile)
    assert profile.name == "Test Kandidat"
    assert profile.role_gesucht == "Junior AI Engineer"
    # praeferenzen ist ein dict, kein Objekt — Zugriff über []
    assert profile.praeferenzen["level"] == "Junior"
    assert profile.praeferenzen["standort"] == "Hamburg oder Remote"


# --- build_system_prompt --------------------------------------------------


def _example_profile() -> Profile:
    """Realistisches Beispielprofil für die Prompt-Tests."""
    return Profile(
        name="Sung-Hack Hong",
        role_gesucht="Junior AI Engineer",
        erfahrung=[
            "B.Sc. Angewandte Informatik, HAW Hamburg",
            "2 Jahre Salesforce Developer",
        ],
        zertifikate=["Anthropic: Claude API, Claude Code 101"],
        kernskills=["Python (Type Hints, async/await)", "LangGraph"],
        portfolio_projekte=["RAG-System über technische Doku"],
        praeferenzen={
            "level": "ausschliesslich Junior/Entry-Level",
            "standort": "Hamburg oder Remote",
        },
    )


def test_build_system_prompt_enthaelt_alle_profil_felder() -> None:
    """Der Prompt muss jeden Profilwert wörtlich enthalten — sonst
    bewertet das Modell an einem unvollständigen Bild vorbei."""
    profile = _example_profile()
    prompt = build_system_prompt(profile)

    # Basisfelder wörtlich im Prompt
    assert profile.name in prompt
    assert profile.role_gesucht in prompt

    # Alle Listen-Einträge müssen einzeln auftauchen
    for item in profile.erfahrung:
        assert item in prompt
    for item in profile.zertifikate:
        assert item in prompt
    for item in profile.kernskills:
        assert item in prompt
    for item in profile.portfolio_projekte:
        assert item in prompt

    # Präferenzen — Schlüssel UND Wert müssen im Prompt landen
    for schluessel, wert in profile.praeferenzen.items():
        assert schluessel in prompt
        assert wert in prompt


def test_build_system_prompt_enthaelt_junior_kriterien_und_anker() -> None:
    """Der Prompt muss die Junior-Tauglichkeits-Anweisung und die
    Score-Anker enthalten — diese steuern das Bewertungsverhalten."""
    prompt = build_system_prompt(_example_profile())

    # Kernaussage der Junior-Anweisung
    assert "Junior-Tauglichkeit" in prompt
    assert "WICHTIGSTE" in prompt
    # Ein Beispiel-Signal wörtlich, damit klar ist dass die Beispiele
    # im Prompt drin sind (nicht wegoptimiert)
    assert "eigenständige Architektur-Entscheidungen" in prompt

    # Score-Anker-Ranges müssen erkennbar sein (Repräsentanten pro Bucket)
    assert "0.9-1.0" in prompt
    assert "0.7-0.89" in prompt
    assert "0.5-0.69" in prompt
    assert "0.3-0.49" in prompt
    assert "0.0-0.29" in prompt

    # Format-Regeln für den strukturierten Output
    assert "reasoning" in prompt
    assert "matched_skills" in prompt
    assert "missing_skills" in prompt

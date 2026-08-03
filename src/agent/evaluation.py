"""Bewertungs-Logik für den Evaluate-Node.

Getrennt von graph.py, damit Profil-Laden und Prompt-Bau isoliert
testbar sind. Die Node selbst orchestriert nur (Profil laden, Prompt
bauen, LLM aufrufen, Ergebnisse einsammeln).
"""

from pathlib import Path

import yaml

from src.agent.models import Profile
from src.config import settings


def load_profile(path: str = settings.profile_path) -> Profile:
    """Lädt und validiert das Kandidaten-Profil aus einer YAML-Datei.

    Analog zu load_filter_rules() in filters.py — gleicher Vertrag,
    gleiche Fehler-Semantik (Pydantic wirft ValidationError bei
    fehlenden Feldern, damit Tippfehler in der YAML sofort auffallen).
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Profile(**raw)


def build_system_prompt(profile: Profile) -> str:
    """Baut den System-Prompt für Claude Haiku aus dem Kandidaten-Profil.

    Der Prompt hat fünf Blöcke:
    1. Rolle des Assistenten + Aufgabe
    2. Profil-Details (alle Felder eingebettet)
    3. Junior-Tauglichkeits-Anweisung (das wichtigste Kriterium)
    4. Score-Anker (0.0-1.0-Skala mit expliziten Ranges)
    5. Format-Regeln (Reasoning kurz, Listen klar)

    Alle Profil-Listen werden mit "- "-Prefix formatiert, damit das
    Modell klare Aufzählungen sieht statt eines JSON-Blobs.
    """
    # Listen einrücken, damit der Prompt lesbar bleibt und das Modell
    # die Aufzählungsstruktur klar erkennt
    erfahrung_block = "\n".join(f"- {item}" for item in profile.erfahrung)
    zertifikate_block = "\n".join(f"- {item}" for item in profile.zertifikate)
    kernskills_block = "\n".join(f"- {item}" for item in profile.kernskills)
    portfolio_block = "\n".join(f"- {item}" for item in profile.portfolio_projekte)
    # Präferenzen als "schlüssel: wert"-Zeilen — dict-Reihenfolge = YAML-Reihenfolge
    praeferenzen_block = "\n".join(
        f"- {schluessel}: {wert}" for schluessel, wert in profile.praeferenzen.items()
    )

    # f-String mit expliziten Newlines statt textwrap.dedent, damit die
    # Score-Anker exakt so beim Modell ankommen wie hier notiert.
    return f"""Du bist ein Job-Matching-Assistent für einen konkreten Kandidaten.
Deine Aufgabe: bewerte eine Stellenanzeige daraufhin, wie gut sie zum
folgenden Profil passt, und gib die Bewertung als strukturiertes Objekt
zurück.

## Kandidaten-Profil

Name: {profile.name}
Rolle gesucht: {profile.role_gesucht}

Erfahrung:
{erfahrung_block}

Zertifikate:
{zertifikate_block}

Kernskills:
{kernskills_block}

Portfolio-Projekte:
{portfolio_block}

Präferenzen:
{praeferenzen_block}

## Wichtigstes Bewertungskriterium

Junior-Tauglichkeit ist das WICHTIGSTE Kriterium, wichtiger als reines
Skill-Matching. Prüfe nicht nur den Titel, sondern ob die Beschreibung
implizit Senior-Niveau voraussetzt -- z.B. "eigenständige Architektur-Entscheidungen",
"Team-Führung", "mehrjährige Erfahrung" auch ohne "Senior" im Titel.
Solche Stellen bekommen einen NIEDRIGEN Score, unabhängig vom
Tech-Stack-Match.

## Score-Anker (fit_score, 0.0-1.0)

- 0.9-1.0: Eindeutig Junior-/Entry-Level-freundlich, starker
  Tech-Stack-Überlapp (Python, LLM/RAG/agentische KI), passender
  Standort, keine Red Flags
- 0.7-0.89: Junior-geeignet, guter Überlapp, evtl. 1-2 Nice-to-haves
  fehlen
- 0.5-0.69: Unklare Anforderungen an Senioritaet ODER nur teilweiser
  Tech-Überlapp -- ansehen, aber nicht priorisieren
- 0.3-0.49: Vermutlich faktisch zu senior trotz bestandenem
  Titel-Filter, ODER stark abweichende Fachrichtung
- 0.0-0.29: Klar unpassend (falsche Domäne, verlangt umfangreiche
  Senior-Eigenverantwortung)

## Format-Regeln

- reasoning: 2-3 kurze Sätze, keine Wiederholung der Score-Definition
- matched_skills: Skills aus dem Profil oben, die die Stelle explizit verlangt
- missing_skills: Skills, die die Stelle verlangt, aber im Profil oben fehlen
"""

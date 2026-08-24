"""Filter-Logik für den Filter-Node.

Getrennt von graph.py, damit die einzelnen Regel-Checks isoliert testbar
sind und die Node selbst nur noch orchestriert (State lesen, Checks
aufrufen, State schreiben).

Alle Checks folgen demselben Vertrag:
    Rückgabe = None            -> Job hat den Check bestanden
    Rückgabe = str (Grund)     -> Job wurde abgelehnt, String erklärt warum
Damit lässt sich filter_job() als simple Kette formulieren.
"""

import re

from sqlalchemy.orm import Session

from src.agent.models import FilterRules, Job
from src.db.repository import get_filter_rules

# Vorab kompilierte Regex — spart pro-Job-Kompilierung im Hot Path.
# Match-Beispiele: "5 Jahre", "3+ years", "10 Jahre".
# Absichtlich einfach: bei "3-5 Jahre" matched sie nur "5" (der Bindestrich
# ist kein \d, also startet der Match bei der 5). Range-Behandlung wäre
# Overengineering für den ersten Wurf.
_EXPERIENCE_PATTERN = re.compile(r"(\d+)\+?\s*(Jahre|years)", re.IGNORECASE)


def load_filter_rules(session: Session) -> FilterRules:
    """Lädt und validiert die Filterregeln aus der Datenbank.

    Bis M2 wurden die Regeln aus data/filter_rules.yaml gelesen. Seit
    der Seed-Migration ac7556d5370e liegen sie in der filter_rules-
    Tabelle und sind über die API editierbar. Der YAML-Pfad in
    settings.filter_rules_path bleibt in der Config bestehen, wird
    aber nicht mehr gelesen.

    Parameter:
        session: aktive SQLAlchemy-Session (der Aufrufer verwaltet
                 Öffnen und Schließen — analog zu save_evaluated_job).

    Rückgabe:
        FilterRules-Instanz. get_filter_rules() wirft RuntimeError,
        wenn die Seed-Zeile fehlt (Migration nicht angewendet).
    """
    return get_filter_rules(session)


def check_title_blacklist(job: Job, rules: FilterRules) -> str | None:
    """Prüft, ob ein Blacklist-Wort als Substring im Titel vorkommt.

    Case-insensitive per .lower() auf beiden Seiten. Substring reicht,
    weil "Senior" auch "Senior Data Scientist" fangen soll.
    """
    title_lower = job.title.lower()
    for term in rules.title_blacklist:
        if term.lower() in title_lower:
            # Original-Schreibweise des Terms zurückgeben, nicht die
            # lowercase-Variante — lesbarere Begründung
            return f"title_blacklist: {term}"
    return None


def check_experience(job: Job, rules: FilterRules) -> str | None:
    """Sucht Erfahrungs-Angaben in Titel + Beschreibung und lehnt ab,
    wenn die höchste gefundene Zahl über max_experience_years liegt.

    Wichtig: bei mehreren Treffern zählt der HÖCHSTE Wert (worst case).
    Beispiel: "3 Jahre Python, 5 Jahre Cloud" -> es zählt die 5,
    nicht die erste gefundene 3. So filtern wir konservativ.
    """
    # Titel + Beschreibung zusammen durchsuchen — einige Anzeigen packen
    # die Erfahrungs-Angabe in den Titel, andere in die Description
    combined = f"{job.title} {job.description}"
    matches = _EXPERIENCE_PATTERN.findall(combined)
    if not matches:
        return None
    # findall gibt bei zwei Capture-Groups eine Liste von Tupeln zurück:
    # [("5", "Jahre"), ("3", "years")]. Uns interessiert nur die Zahl.
    highest = max(int(zahl) for zahl, _ in matches)
    if highest > rules.max_experience_years:
        return f"experience: {highest} Jahre gefordert (max {rules.max_experience_years})"
    return None


def check_description_blacklist(job: Job, rules: FilterRules) -> str | None:
    """Prüft, ob eine Blacklist-Phrase als Substring in der Beschreibung
    vorkommt. Case-insensitive, gleiche Logik wie check_title_blacklist.
    """
    description_lower = job.description.lower()
    for phrase in rules.description_blacklist:
        if phrase.lower() in description_lower:
            return f"description_blacklist: {phrase}"
    return None


def filter_job(job: Job, rules: FilterRules) -> str | None:
    """Führt alle drei Checks aus und gibt beim ersten Treffer ab.

    Kurzschluss-Verhalten ist Absicht: sobald ein Grund gefunden ist,
    brauchen wir die anderen Checks nicht mehr — spart Zeit bei langen
    Beschreibungen und hält die Begründung eindeutig (ein Grund pro Job).
    """
    for check in (
        check_title_blacklist,
        check_experience,
        check_description_blacklist,
    ):
        reason = check(job, rules)
        if reason is not None:
            return reason
    return None

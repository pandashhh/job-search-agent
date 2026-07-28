"""
Manueller End-to-End-Check: kompletter LangGraph-Lauf ohne jegliches Mocking.

Startet den echten jobspy-MCP-Server als Subprozess (via search_node),
ruft die echte Anthropic-API auf (via evaluate_node) und schreibt am Ende
eine kompakte Übersicht auf die Konsole. Kein pytest — direkt mit
`python` ausführen, verursacht echte API-Kosten.

Ausführen:
    python tests/manual/full_agent_run_check.py

Voraussetzungen:
    - .env mit ANTHROPIC_API_KEY
    - data/profile.yaml (nicht die .example-Datei) vorhanden
    - data/filter_rules.yaml vorhanden
"""

import asyncio
import sys
from pathlib import Path

# Projekt-Root manuell zu sys.path hinzufügen — nötig, weil dieses Skript
# direkt ausgeführt wird (python tests/manual/full_agent_run_check.py),
# nicht über pytest (das pythonpath aus pytest.ini nutzt)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agent.graph import build_graph


async def main() -> None:
    # Graph einmal bauen — build_graph() ist synchron, kompiliert die
    # StateGraph zu einem ausführbaren Graphen
    graph = build_graph()

    # Vollständiger Initial-State: alle Listen leer, Suchparameter gesetzt.
    # LangGraph erwartet, dass ALLE TypedDict-Keys vorhanden sind (auch
    # die, die von den Nodes befüllt werden) — sonst KeyError im Node.
    initial_state = {
        "search_term": "Junior AI Engineer",
        "location": "Hamburg",
        "raw_jobs": [],
        "filtered_jobs": [],
        "rejected_jobs": [],
        "evaluated_jobs": [],
        "errors": [],
    }

    print("Starte kompletten Agenten-Lauf (echter MCP + echte Anthropic-API)...\n")
    result = await graph.ainvoke(initial_state)

    # --- Kompakte Übersicht ---
    # Zahlen zuerst, damit man auf einen Blick sieht, wo der Trichter greift
    print("=" * 60)
    print("Ergebnisübersicht")
    print("=" * 60)
    print(f"raw_jobs:       {len(result['raw_jobs'])}")
    print(f"filtered_jobs:  {len(result['filtered_jobs'])}")
    print(f"rejected_jobs:  {len(result['rejected_jobs'])}")
    print(f"evaluated_jobs: {len(result['evaluated_jobs'])}")

    # Fehler ausgeben, falls welche gesammelt wurden — Nodes werfen nicht,
    # sondern sammeln in errors[], damit der Rest des Graphen weiterläuft
    if result["errors"]:
        print("\n--- Fehler ---")
        for fehler in result["errors"]:
            print(f"  - {fehler}")

    # Rejected Jobs: nur Titel + Ablehnungsgrund, sonst uninteressant
    if result["rejected_jobs"]:
        print("\n--- Abgelehnt (Filter-Node) ---")
        for rejected in result["rejected_jobs"]:
            print(f"  - [{rejected.rejection_reason}] {rejected.job.title}")

    # Bewertete Jobs: nach fit_score DESC sortiert, damit die relevantesten
    # Jobs oben stehen — key=lambda greift auf das verschachtelte
    # evaluation.fit_score zu (EvaluatedJob.evaluation ist ein JobEvaluation)
    if result["evaluated_jobs"]:
        print("\n--- Bewertet (nach fit_score absteigend) ---")
        sortiert = sorted(
            result["evaluated_jobs"],
            key=lambda ej: ej.evaluation.fit_score,
            reverse=True,
        )
        for evaluated in sortiert:
            print(
                f"\n  [{evaluated.evaluation.fit_score:.2f}] "
                f"{evaluated.job.title} @ {evaluated.job.company}"
            )
            # Reasoning eingerückt, damit die Zuordnung zum Job klar bleibt
            print(f"      {evaluated.evaluation.reasoning}")


if __name__ == "__main__":
    asyncio.run(main())

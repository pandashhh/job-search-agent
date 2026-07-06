"""
Smoke-Test für den LangGraph-Graphen.

Dieser Test prüft nur, dass der Graph korrekt kompiliert und die
Platzhalter-Nodes ohne Fehler durchlaufen werden — nicht die eigentliche
Node-Logik. Die Tests für Search, Filter und Evaluate folgen in #6/#7/#8.
"""

import pytest

from src.agent.graph import build_graph


@pytest.mark.asyncio
async def test_graph_baut_und_laeuft_durch() -> None:
    """Kompiliert den Graphen und führt ihn mit leerem Dummy-Input durch.

    Da alle Nodes aktuell {} zurückgeben, darf der State unverändert
    bleiben — kein Node darf die Eingangs-Listen kaputt machen oder
    auf None setzen.
    """
    graph = build_graph()

    result = await graph.ainvoke(
        {
            "search_term": "Junior AI Engineer",
            "location": "Hamburg",
            "raw_jobs": [],
            "filtered_jobs": [],
            "rejected_jobs": [],
            "evaluated_jobs": [],
            "errors": [],
        }
    )

    assert result is not None

    # Platzhalter-Nodes geben {} zurück — LangGraph merged das in den State,
    # d.h. die leeren Listen aus dem Input bleiben erhalten
    assert result["raw_jobs"] == []
    assert result["filtered_jobs"] == []
    assert result["rejected_jobs"] == []
    assert result["evaluated_jobs"] == []

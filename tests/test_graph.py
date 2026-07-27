"""
Smoke-Test für den LangGraph-Graphen.

Prüft nur, dass der Graph korrekt kompiliert und alle Nodes ohne Fehler
durchlaufen werden — nicht die eigentliche Node-Logik. Die Logik-Tests
für Search, Filter und Evaluate leben in test_search_node.py usw.

search_jobs_via_mcp wird gemockt, damit kein echter MCP-Server-Prozess
gestartet wird und der Test als reiner Struktur-Test bleibt.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent.graph import build_graph


@pytest.mark.asyncio
async def test_graph_baut_und_laeuft_durch() -> None:
    """Kompiliert den Graphen und führt ihn mit leerem Dummy-Input durch.

    search_jobs_via_mcp gibt eine leere Liste zurück — der Search-Node
    schreibt damit raw_jobs=[] in den State. Filter, Evaluate und Store
    sind noch Platzhalter und verändern den State nicht.
    """
    # Mock auf der Stelle, wo graph.py die Funktion importiert hat
    with patch(
        "src.agent.graph.search_jobs_via_mcp",
        new_callable=AsyncMock,
        return_value=[],
    ):
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
    assert result["raw_jobs"] == []
    assert result["filtered_jobs"] == []
    assert result["rejected_jobs"] == []
    assert result["evaluated_jobs"] == []

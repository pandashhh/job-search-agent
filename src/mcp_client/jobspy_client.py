"""MCP-Client-Wrapper für den jobspy-Server.

Stellt search_jobs_via_mcp() als wiederverwendbare async Funktion bereit.
Startet den Server-Prozess bei jedem Aufruf neu (stdio-Transport) — bei
einem Lauf pro Tag ist das keine relevante Optimierung.

Gibt rohe dicts zurück, kein Mapping auf Job-Modelle — das bleibt Aufgabe
des aufrufenden Nodes, damit dieses Modul unabhängig vom Graph-State bleibt.
"""

import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Projekt-Root: drei Ebenen über dieser Datei (src/mcp_client/ → Projekt-Root)
_PROJECT_ROOT = Path(__file__).parent.parent.parent


async def search_jobs_via_mcp(
    search_term: str,
    location: str,
    site_names: list[str] | None = None,
    results_wanted: int = 15,
) -> list[dict]:
    """Ruft das Tool search_jobs auf dem jobspy-MCP-Server auf.

    Startet den Server als Subprozess, führt den initialize-Handshake durch,
    ruft das Tool auf und gibt die geparste Liste von Job-Dicts zurück.

    Args:
        search_term: Suchbegriff, z.B. "Junior AI Engineer"
        location: Stadt oder Region, z.B. "Hamburg"
        site_names: Jobportale, default ["indeed"]
        results_wanted: Maximale Anzahl Ergebnisse pro Portal

    Returns:
        Liste von Job-Dicts (rohe Felder aus JobSpy, unverändert)

    Raises:
        RuntimeError: Wenn der Server einen {"error": "..."} zurückgibt
    """
    # Default hier setzen, nicht als Funktionssignatur-Default — vermeidet
    # das mutable-default-argument-Problem mit Listen in Python
    if site_names is None:
        site_names = ["indeed"]

    # StdioServerParameters: beschreibt nur den Startbefehl, startet noch keinen Prozess
    server_params = StdioServerParameters(
        command=str(_PROJECT_ROOT / "venv" / "bin" / "python"),
        args=[str(_PROJECT_ROOT / "mcp_servers" / "jobspy_server" / "server.py")],
        # cwd zur Sicherheit explizit gesetzt, auch wenn hier nicht zwingend nötig
        cwd=str(_PROJECT_ROOT),
    )

    # stdio_client startet den Subprozess und öffnet zwei In-Memory-Streams
    # (read_stream: Antworten vom Server, write_stream: Anfragen an den Server)
    async with stdio_client(server_params) as (read_stream, write_stream):

        # ClientSession kapselt das MCP-Protokoll — initialize() ist Pflicht,
        # sonst lehnt der Server alle weiteren Anfragen ab
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # call_tool() sendet die JSON-RPC-Anfrage und wartet auf die Antwort
            result = await session.call_tool(
                "search_jobs",
                arguments={
                    "search_term": search_term,
                    "location": location,
                    "site_names": site_names,
                    "results_wanted": results_wanted,
                },
            )

            if result.isError:
                error_text = result.content[0].text if result.content else "unbekannter MCP-Fehler"
                raise RuntimeError(f"MCP-Protokollfehler: {error_text}")


            # result.content[0].text enthält den JSON-String aus search_jobs()
            raw_json: str = result.content[0].text  # type: ignore[union-attr]
            parsed = json.loads(raw_json)

            # Server gibt bei Fehlern {"error": "..."} zurück (kein Absturz des
            # Server-Prozesses), aber hier soll der Aufrufer eine echte Exception sehen
            if isinstance(parsed, dict) and "error" in parsed:
                raise RuntimeError(f"jobspy-Server-Fehler: {parsed['error']}")

            return parsed  # type: ignore[return-value]

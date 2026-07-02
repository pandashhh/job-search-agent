"""
Manueller Integrationstest: jobspy-MCP-Server via stdio-Transport.

Startet den Server als Subprozess, baut eine MCP-ClientSession auf und
ruft das Tool "search_jobs" auf. Kein pytest — direkt mit `python` ausführen.

Ausführen:
    python tests/manual/test_jobspy_client.py
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Projektverzeichnis: zwei Ebenen über dieser Datei (tests/manual/ → Projekt-Root)
PROJECT_ROOT = Path(__file__).parent.parent.parent


async def main() -> None:
    # StdioServerParameters beschreibt, wie der MCP-Server-Prozess gestartet wird.
    # `command` ist das Python-Executable im venv, `args` übergibt das Server-Skript.
    # `cwd` ist nötig, damit relative Imports im Server korrekt aufgelöst werden.
    server_params = StdioServerParameters(
        command=str(PROJECT_ROOT / "venv" / "bin" / "python"),
        args=[str(PROJECT_ROOT / "mcp_servers" / "jobspy_server" / "server.py")],
        cwd=str(PROJECT_ROOT),
    )

    # stdio_client ist ein Async-Kontextmanager: er startet den Subprozess und öffnet
    # zwei In-Memory-Streams — read_stream (Antworten vom Server) und write_stream
    # (Anfragen an den Server). Beide folgen dem JSON-RPC-Protokoll von MCP.
    async with stdio_client(server_params) as (read_stream, write_stream):

        # ClientSession kapselt das MCP-Protokoll: initialize-Handshake, Tool-Aufrufe,
        # Ressourcen-Listing usw. Sie kommuniziert über die übergebenen Streams.
        async with ClientSession(read_stream, write_stream) as session:

            # initialize() führt den MCP-Handshake durch: der Client sendet seine
            # Fähigkeiten, der Server antwortet mit seinen Tools und Ressourcen.
            # Ohne diesen Schritt lehnt der Server alle weiteren Anfragen ab.
            await session.initialize()

            print("Server initialisiert. Rufe 'search_jobs' auf ...\n")

            # call_tool() sendet eine JSON-RPC-Anfrage an den Server und wartet
            # auf die Antwort. Die Parameter müssen als dict übergeben werden und
            # müssen exakt den Parameternamen des Tools entsprechen.
            result = await session.call_tool(
                "search_jobs",
                arguments={
                    "search_term": "Junior AI Engineer",
                    "location": "Hamburg",
                    "site_names": ["indeed"],
                    "results_wanted": 10,
                },
            )

            # result.content ist eine Liste von ContentBlock-Objekten.
            # Jeder TextContent-Block hat ein `.text`-Feld mit dem Rückgabewert des Tools.
            raw_json = result.content[0].text  # type: ignore[union-attr]

            # Rohen JSON-String parsen und formatiert ausgeben
            jobs = json.loads(raw_json)
            print(f"Gefundene Jobs: {len(jobs)}\n")
            print(json.dumps(jobs, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

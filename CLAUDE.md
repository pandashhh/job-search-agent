# Claude Code — Projektregeln: job-search-agent

## Ziel
KI-Agent, der Jobportale durchsucht, Ergebnisse filtert und nach Passung
zum eigenen Profil bewertet. Junior AI Engineer Portfolio-Projekt.

## Sprache & Kommentare
- Kommentare im Code auf Deutsch
- Jede nicht-triviale Zeile kommentieren — das Warum, nicht nur das Was
- Bei Funktionen: Zweck, Parameter und Rückgabewert kurz erklären

## Code-Qualität
- Type Hints für alle Parameter und Rückgabewerte (->)
- async/await konsequent für I/O-Operationen
- Pydantic BaseSettings für Konfiguration, BaseModel für Datenmodelle
- Fehlerbehandlung mit spezifischen Exceptions, nie nur `except Exception`
- Singleton-Pattern für Clients (einmal erstellen, überall wiederverwenden)

## Architektur
Pipeline: Search-Node → Filter-Node → Bewertungs-Node → Storage-Node
(LangGraph StateGraph, aufbauend auf research-agent, aber linearer statt
Koordinator+Sub-Agenten, da kein dynamisches Delegieren nötig ist)

- **Datenquelle**: selbstgebauter MCP-Server (`mcp_servers/jobspy_server/`),
  kapselt die `python-jobspy`-Bibliothek. Siehe "Entscheidungen" unten.
- **DB**: PostgreSQL + pgvector-Extension (keine separate Vektor-DB)
- **Bewertung**: Claude Haiku (claude-haiku-4-5-20251001), wie research-agent
- **API**: FastAPI
- **Frontend**: einfaches Dashboard, Design via frontend-design Skill
- **Monitoring**: Langfuse
- **Deployment**: GCP Cloud Run + GitHub Actions CD + Cloud Scheduler

## Wichtige Entscheidungen
- **jobspy-mcp-server selbst gebaut, statt fertigen Wrapper genutzt.**
  Offizieller Indeed-MCP-Server ist an Anthropics Connector-Infrastruktur
  gebunden, kein eigener Client möglich. `borgius/jobspy-mcp-server`
  braucht Node.js + ein unklar referenziertes Sibling-Repo, kein echtes
  Dockerfile trotz anderslautender Aggregator-Angaben.
  `chinpeerapat/jobspy-mcp-server` hat kaputte Dependency
  (`jobspy>=1.1.82` existiert nicht auf PyPI). Lösung: eigener
  FastMCP-Server um `python-jobspy` (speedyapply/JobSpy, aktiv gepflegt,
  2.9k Stars) — gleiches Pattern wie `rag-mcp-server`.
- `country_indeed="Germany"` ist in `search_jobs()` fest als Default
  gesetzt — ohne diesen Parameter liefert JobSpy US-Ergebnisse statt
  Hamburg. `location` grenzt nur *innerhalb* eines Landes ein,
  `country_indeed` bestimmt, welches Land überhaupt durchsucht wird.
- Filter-Regeln liegen in der DB (`filter_rules`-Tabelle), nicht hart
  codiert — anpassbar über API/Frontend
- Dedup-Check (`jobs.external_id`) läuft VOR dem Bewertungs-Node, damit
  bekannte Jobs nicht erneut per LLM bewertet werden (Kostenersparnis)
- pgvector-Embeddings primär für Duplikat-Erkennung über mehrere Quellen

## Anthropic API
- Modell für Bewertungs-Node: claude-haiku-4-5-20251001
- Immer AsyncAnthropic, nie sync Anthropic

## LangGraph
- StateGraph mit TypedDict/Pydantic für State
- Nodes: Search → Filter → Bewertung → Storage (linear, keine Conditional
  Edges nötig, da kein dynamisches Delegieren)

## MCP
- FastMCP für den jobspy-Server (`mcp_servers/jobspy_server/server.py`)
- stdio Transport (lokal, wie rag-mcp-server)
- Jedes Tool: klarer Name, Docstring als Description, Type Hints
- Agent-Seite wird MCP-Client (neu: bisher nur Server gebaut)

## Testing
- Immer mocken: API-Calls, DB, externe Services (inkl. MCP-Client)
- pytest-asyncio für async Tests
- Keine echten Scraping-Calls in Tests (JobSpy-Aufrufe mocken)

## Tech-Stack
Python 3.11.3 (pyenv local), LangGraph, LangChain, Anthropic SDK, FastAPI,
SQLAlchemy, Alembic, PostgreSQL + pgvector, python-jobspy, FastMCP, Docker,
pytest

## Projektstruktur
- `src/agent/` — LangGraph State, Nodes, Graph
- `src/api/` — FastAPI App, Routes
- `src/db/` — SQLAlchemy-Modelle, DB-Verbindung
- `src/mcp_client/` — MCP-Client-Wrapper (Agent-Seite → jobspy_server)
- `mcp_servers/jobspy_server/` — eigener MCP-Server um python-jobspy
- `tests/` — gespiegelt zu `src/`
- `docker/` — Dockerfiles, docker-compose
- `docs/` — u.a. JobSpy-Parameter-Doku

## Git-Workflow
- Branch pro Issue: `<issue-nummer>-<kurzbeschreibung>`
- Pull Request mit `Closes #<nummer>` in der Beschreibung
- Ausnahme: kleine Korrekturen an bereits gemergtem Content direkt auf main

## Erklär-Stil für Claude-Code-Sessions
- Jede nicht-triviale Zeile einzeln erklären — das Warum, nicht nur das Was
- Bekannte Konzepte (nicht grundlegend erklären): async/await, Type Hints,
  Pydantic, pytest+Mocking, FastAPI, Docker, GitHub Actions, LangGraph,
  MCP+FastMCP, RAG-Konzepte, Tool Use, Multi-Agent-Pattern
- Noch zu lernen (mit Erklärungen): SQL+PostgreSQL in Python
  (SQLAlchemy/psycopg2), Langfuse, GCP Cloud Run, CD-Pipelines, Frontend

## Verwandte Projekte (Referenz für Patterns)
- research-agent — LangGraph-Patterns, Sub-Agenten-Struktur
- anthropic-docs-rag — Docker-Optimierung (9GB→2GB), Embedding-Caching
- rag-mcp-server — MCP-Server-Patterns (Vorlage für jobspy_server)

## Roadmap
21 Issues über 6 Meilensteine auf GitHub, gruppiert per Label
(`m1-datenquelle` bis `m6-deployment`). Siehe
github.com/pandashhh/job-search-agent/issues
# job-search-agent

## Ziel
KI-Agent, der Jobportale durchsucht, Ergebnisse filtert und nach Passung zum
eigenen Profil bewertet. Junior AI Engineer Portfolio-Projekt.

## Architektur
Pipeline: Search-Node → Filter-Node → Bewertungs-Node → Storage-Node
(LangGraph StateGraph, aufbauend auf research-agent, aber linearer statt
Koordinator+Sub-Agenten, da kein dynamisches Delegieren nötig ist)

- **Datenquelle**: jobspy-mcp-server (self-hosted, Docker) statt Indeed API
  direkt — der offizielle Indeed-MCP-Server ist an den Claude-Connector
  gebunden und nicht für eigene Clients nutzbar.
- **DB**: PostgreSQL + pgvector-Extension (keine separate Vektor-DB, um
  strukturierte Filter und Embeddings in einer DB zu halten)
- **Bewertung**: Claude Haiku, wie in research-agent
- **API**: FastAPI
- **Frontend**: einfaches Dashboard, Design via frontend-design Skill
- **Monitoring**: Langfuse
- **Deployment**: GCP Cloud Run + GitHub Actions CD + Cloud Scheduler

## Wichtige Entscheidungen
- Filter-Regeln liegen in der DB (`filter_rules`-Tabelle), nicht hart codiert
  — Nutzer kann sie über die API/Frontend anpassen
- Dedup-Check (via `jobs.external_id`) läuft VOR dem Bewertungs-Node, damit
  bereits bekannte Jobs nicht erneut per LLM bewertet werden (Kostenersparnis)
- pgvector-Embeddings primär für Duplikat-Erkennung über mehrere Quellen
  (JobSpy durchsucht Indeed+LinkedIn+Glassdoor, gleiche Stelle taucht
  mehrfach auf)

## Tech-Stack
Python 3.11.3 (pyenv local), LangGraph, LangChain, Anthropic SDK, FastAPI,
SQLAlchemy, Alembic, PostgreSQL + pgvector, Docker, pytest

## Konventionen
- Code-Kommentare auf Deutsch
- Tests: immer vollständig gemockt (AsyncMock/patch), keine echten API-Calls
- Type Hints + Pydantic-Modelle durchgängig
- API-Key niemals im Code oder Repo — nur über `.env` (siehe `.gitignore`)

## Projektstruktur
- `src/agent/` — LangGraph State, Nodes, Graph
- `src/api/` — FastAPI App, Routes
- `src/db/` — SQLAlchemy-Modelle, DB-Verbindung
- `src/mcp_client/` — MCP-Client-Wrapper für jobspy-mcp-server
- `tests/` — gespiegelt zu `src/`
- `docker/` — Dockerfiles, docker-compose
- `docs/` — u.a. JobSpy-Parameter-Doku

## Verwandte Projekte (Referenz für Patterns)
- research-agent — LangGraph-Patterns, Sub-Agenten-Struktur
- anthropic-docs-rag — Docker-Optimierung (9GB→2GB), Embedding-Caching
- rag-mcp-server — MCP-Server-Patterns (hier: Client statt Server)

## Roadmap
21 Issues über 6 Meilensteine auf GitHub, gruppiert per Label
(`m1-datenquelle` bis `m6-deployment`). Siehe
github.com/pandashhh/job-search-agent/issues
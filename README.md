# Job Search Agent

KI-Agent, der Jobportale durchsucht, Ergebnisse filtert und nach Passung
zum eigenen Profil bewertet — von der Suche bis zum durchsuchbaren
Dashboard.

![CI](https://github.com/pandashhh/job-search-agent/actions/workflows/ci.yml/badge.svg)

## Warum dieses Projekt

Klassische Jobsuche bedeutet: dieselben Suchbegriffe auf mehreren Portalen
wiederholen, Dutzende Stellenanzeigen lesen, bei denen "5+ Jahre Erfahrung"
schon im zweiten Satz disqualifiziert. Dieser Agent automatisiert Suche,
Vorfilterung und Bewertung — und lernt dabei, welche Stellen tatsächlich
zum eigenen Profil passen.

## Architektur

```mermaid
flowchart LR
    A["Eigener jobspy MCP-Server<br/>(python-jobspy)"] -->|MCP| B[Search Node]
    B --> C[Filter Node<br/>regelbasiert]
    C --> D[Bewertungs Node<br/>Claude Haiku]
    D --> E[(PostgreSQL<br/>+ pgvector)]
    E --> F[FastAPI]
    F --> G[Dashboard]
```

LangGraph-Pipeline: Search → Filter → Bewertung → Storage. Details und
Architektur-Entscheidungen in [CLAUDE.md](./CLAUDE.md).

## Tech-Stack

Python 3.11 · LangGraph · Anthropic Claude (Haiku) · FastAPI · PostgreSQL
+ pgvector · Docker · Langfuse · GCP Cloud Run

## Status

🚧 In aktiver Entwicklung. Fortschritt und Roadmap:
[GitHub Issues](https://github.com/pandashhh/job-search-agent/issues)
(21 Issues über 6 Meilensteine)

## Verwandte Projekte

- [research-agent](https://github.com/pandashhh/research-agent) —
  Multi-Agent-System mit LangGraph
- [anthropic-docs-rag](https://github.com/pandashhh/anthropic-docs-rag) —
  RAG-System mit Docker-Optimierung
- [rag-mcp-server](https://github.com/pandashhh/rag-mcp-server) —
  MCP-Server-Implementierung

## Setup

Voraussetzungen: Python 3.11 (via pyenv)

```bash
git clone https://github.com/pandashhh/job-search-agent.git
cd job-search-agent
pyenv local 3.11.3
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # nur für Entwicklung/Tests
alembic upgrade head  # wendet alle Migrationen an und bringt die DB auf den aktuellen Schema-Stand
```

Die Initial-Migration versucht `CREATE EXTENSION IF NOT EXISTS vector`
für pgvector. In lokalen und den meisten Managed-Postgres-Setups (Cloud
SQL, Supabase) hat der DB-User dieses Recht bereits. In strikt getrennten
Setups (App-User ohne Superuser-Rolle) muss die Extension einmalig als
Superuser angelegt werden, bevor `alembic upgrade head` läuft:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### HTTP-API starten

Nach dem Setup läuft die FastAPI-App lokal mit uvicorn (Hot-Reload für
Entwicklung, sonst ohne `--reload`):

```bash
uvicorn src.api.main:app --reload
```

Endpoints:
- `GET  /jobs?min_score=0.5&status_filter=neu&limit=50&offset=0` — bewertete
  Jobs mit Filter und Pagination
- `PATCH /jobs/{job_id}/status` — Bewerbungs-Status setzen (Body:
  `{"status": "beworben"}`)
- `GET  /filter-rules` und `PUT /filter-rules` — Regelwerk lesen/pflegen
- `POST /search-runs` — kompletten Suchlauf anstoßen (Body:
  `{"search_term": "...", "location": "..."}`) — blockiert bis der
  LangGraph-Lauf fertig ist
- `GET  /` — Health-Check

OpenAPI-Doku unter `http://localhost:8000/docs` sobald der Server läuft.

### Frontend starten

React + TypeScript + Vite + Tailwind, im Ordner `frontend/`. Startet
auf `http://localhost:5173` und erwartet das Backend parallel auf
`http://localhost:8000` (CORS-Origin ist genau darauf eingestellt).

```bash
cd frontend
npm install
npm run dev
```

Beim ersten Start sind die Dashboard-Karten leer — über den Tab
"Neuer Suchlauf" den ersten Lauf anstoßen, danach zeigt der Tab "Jobs"
die bewerteten Ergebnisse mit Fit-Score-Badge und Status-Dropdown.
Der Tab "Filter-Regeln" liest/schreibt das Regelwerk direkt in die
DB (Änderungen wirken beim nächsten Suchlauf).

### jobspy MCP-Server (Datenquelle)

Eigener FastMCP-Server um die python-jobspy-Bibliothek (läuft als
Python-Prozess über stdio, kein Docker nötig):

```bash
python mcp_servers/jobspy_server/server.py
```

Manueller Verbindungstest mit einer echten Suchanfrage:
```bash
python tests/manual/jobspy_client_check.py
```
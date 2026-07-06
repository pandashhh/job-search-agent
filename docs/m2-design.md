# M2 — Design-Entscheidungen: LangGraph Agent

Design-Vorarbeit für Issues #5–9, bevor die Umsetzung startet.

## Graph-Topologie

START → search → filter → evaluate → store → END

Strikt linear, kein `num_steps`-Guard (Abweichung vom research-agent-
Template) — es gibt hier keine Conditional Edges/Zyklen, daher nichts,
wovor der Guard schützen müsste. Leere Ergebnisse (keine Treffer, alles
gefiltert) laufen als leere Listen durch die restlichen Nodes durch;
jeder Node behandelt leere Eingaben als No-op.

## State & Datenmodelle

Graph-State als TypedDict, transportierte Objekte als Pydantic-Modelle
in `src/agent/models.py`:

- **Job**: external_id (JobSpys id-Feld, wird Dedup-Key in M3), title,
  company, location, job_url, description, job_type, is_remote,
  date_posted, min_amount, max_amount, site
- **RejectedJob**: job + rejection_reason
- **JobEvaluation**: fit_score (0-1), reasoning, matched_skills,
  missing_skills — zugleich Structured-Output-Schema für Haiku
- **EvaluatedJob**: job + evaluation

State-Felder: search_term, location, raw_jobs, filtered_jobs,
rejected_jobs, evaluated_jobs, errors.

## Search-Node (#6)

MCP-Client-Code aus jobspy_client_check.py wandert aufgeräumt nach
src/mcp_client/jobspy_client.py als wiederverwendbare async Funktion.
Server-Prozess pro Suchlauf (kein dauerhaft laufender Server) — bei
einem Lauf/Tag unnötige Optimierung.

## Filter-Node (#7)

Regeln aus data/filter_rules.yaml (nicht DB, da M3 erst nach M2 kommt),
über load_filter_rules() geladen — Repository-Pattern, Ladefunktion
wird in M3 auf DB umgestellt, Node-Code bleibt unverändert.

Startregeln: title_blacklist (Senior, Lead, Principal, Staff, Head of,
Architekt, Consultant, Berater, Werkstudent, Praktikum),
max_experience_years: 3 (Regex gegen description UND title, da Indeed
kein strukturiertes Erfahrungsfeld liefert — siehe jobspy-notes.md),
description_blacklist (Consulting-Signale).

## Bewertungs-Node (#8)

- Modell: claude-haiku-4-5-20251001, via
  ChatAnthropic(...).with_structured_output(JobEvaluation)
- Profil aus data/profile.yaml — NICHT committed (enthält Gehaltswunsch
  etc.), nur data/profile.example.yaml als Template. Analog .env/.env.example
- Prompt: System = Rolle+Profil+Kriterien, User = Job-Felder
- description ungekürzt (Haiku günstig), max_description_chars als
  Schutz-Guard (Default 8000)
- Erste Version: sequenzielle Bewertung. Parallelisierung mit
  asyncio.gather + Semaphore als spätere Erweiterung

## Storage-Node (Stub)

Schreibt evaluated_jobs als JSON nach data/results/{timestamp}.json
(in .gitignore). Interface store_results(...) bleibt, wird in M3 durch
Postgres-Implementierung ersetzt. Agent ist nach M2 bereits real
nutzbar — täglich laufen lassen, bewertete Jobs als JSON, auch ohne
DB/Frontend.

## Config & Tests

src/config.py mit Pydantic BaseSettings (anthropic_api_key, Modellname,
Pfade). .env + .env.example. tests/conftest.py mit Dummy-Env-Variablen.
Node-Tests entstehen pro PR (#6/#7/#8), #9 ist der E2E-Test.

## Umsetzungsreihenfolge

#5 Gerüst (State, Modelle, Graph-Skelett, Config, conftest) → #6 Search
→ #7 Filter → #8 Evaluate → Storage-Stub → #9 E2E-Test.
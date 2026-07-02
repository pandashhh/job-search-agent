# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`job-search-agent` — a Python-based AI agent for job searching. Python version: 3.11.3 (see `.python-version`).

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # once requirements.txt exists
```

## Development Commands

```bash
# Tests ausführen
pytest

# Einzelnen Test ausführen
pytest tests/test_foo.py::test_bar -v

# Linting
ruff check .

# Formatierung
ruff format .
```

## Code-Konventionen

- Alle Funktionen mit Type Hints versehen
- I/O-Operationen (API-Calls, Datei-Zugriffe) immer `async`
- Umgebungsvariablen ausschließlich über `.env` (nie hardcoded)

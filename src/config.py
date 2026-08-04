"""Zentrale Konfiguration via Pydantic BaseSettings.

Werte werden aus der .env-Datei geladen (python-dotenv ist in BaseSettings
eingebaut). Singleton-Instanz `settings` am Ende des Moduls — überall
importierbar ohne die Klasse neu zu instanziieren.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfigurationsfelder mit Typen und Defaults.

    Felder ohne Default sind Pflichtfelder — fehlen sie in .env,
    wirft Pydantic beim Import einen ValidationError.
    """

    # Anthropic-API-Schlüssel — Pflichtfeld, kein Default
    anthropic_api_key: str

    # Modell für den Bewertungs-Node — Haiku ist schnell und günstig genug
    evaluation_model: str = "claude-haiku-4-5-20251001"

    # Pfad zur YAML-Datei mit den Filterregeln (in M3 durch DB ersetzt)
    filter_rules_path: str = "data/filter_rules.yaml"

    # Profil des Jobsuchenden — NICHT committed (enthält persönliche Daten)
    profile_path: str = "data/profile.yaml"

    # Obergrenze für Job-Beschreibungen im LLM-Prompt (Zeichen, nicht Tokens).
    # Schutz-Guard gegen Ausreißer-Anzeigen; 8000 Zeichen ~ 2000 Tokens,
    # bei Haiku vernachlässigbar teuer.
    max_description_chars: int = 8000

    # Zielverzeichnis für die JSON-Ergebnisdateien des Storage-Nodes.
    # Über Settings konfigurierbar, damit Tests via monkeypatch auf tmp_path
    # umleiten können, ohne das echte data/results/ vollzuschreiben.
    results_dir: str = "data/results"
    # PostgreSQL-Verbindungsstring. Default zeigt auf eine lokale DB ohne
    # User/Passwort (peer-Auth); in CI und Produktion via DATABASE_URL
    # aus der Umgebung überschrieben.
    database_url: str = "postgresql://localhost/job_search_agent"

    # Pydantic-v2-Stil: model_config als Klassenattribut statt verschachtelter
    # class Config. SettingsConfigDict ist der spezialisierte TypedDict-Wrapper
    # von pydantic-settings (statt des generischen ConfigDict aus pydantic).
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Singleton — einmal laden, überall wiederverwenden
settings = Settings()

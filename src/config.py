"""Zentrale Konfiguration via Pydantic BaseSettings.

Werte werden aus der .env-Datei geladen (python-dotenv ist in BaseSettings
eingebaut). Singleton-Instanz `settings` am Ende des Moduls — überall
importierbar ohne die Klasse neu zu instanziieren.
"""

from pydantic_settings import BaseSettings


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

    class Config:
        # .env-Datei im Arbeitsverzeichnis laden
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton — einmal laden, überall wiederverwenden
settings = Settings()

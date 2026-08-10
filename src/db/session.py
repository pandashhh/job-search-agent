"""SQLAlchemy-Engine und Session-Factory für den Agent-Betrieb.

Modul-Level-Singleton wie das Cache-Pattern in src/db/embeddings.py:
Engine und SessionLocal werden einmal beim Import erzeugt, überall
importiert. So teilen sich alle Nodes denselben Connection Pool —
kein neuer Verbindungsaufbau pro Node-Aufruf.

Dieses Modul legt bewusst KEINE Tabellen an. Base.metadata.create_all()
gehört in die Test-Fixture (conftest.py) oder später in eine Alembic-
Migration (siehe Issue #13). Application-Code, der bei jedem Start ein
Schema anlegt, würde in Produktion Migrationen umgehen und Konflikte
verstecken.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings

# Engine: Verbindungs-Pool zur Postgres-DB. create_engine ist lazy —
# die eigentliche Verbindung wird erst bei der ersten Query aufgebaut.
engine = create_engine(settings.database_url)

# sessionmaker gibt eine Klasse zurück, keine Instanz. Aufruf mit
# SessionLocal() erzeugt eine neue Session pro Node/Request.
SessionLocal = sessionmaker(bind=engine)

"""Deklarative Basisklasse für alle ORM-Modelle.

Warum SQLAlchemy 2.0 statt der alten declarative_base()-Funktion:
- Mapped[]-Type-Hints statt Column(...) — der Python-Typ ist zugleich
  die Spaltendefinition, keine doppelte Wahrheit mehr
- Passt zum Projekt-Standard aus CLAUDE.md (Type Hints überall)
- Statische Type-Checker (mypy/pyright) verstehen ORM-Modelle jetzt nativ

Alle ORM-Klassen erben von Base — Base sammelt automatisch die Metadata
(Tabellen, Indizes, FKs) und ist die Wurzel für Base.metadata.create_all().
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Gemeinsame Basisklasse. Bewusst leer — Konfiguration passiert
    pro Modell über Klassenattribute (Mapped[], mapped_column())."""
    pass

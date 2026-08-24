"""seed initial filter_rules from yaml defaults

Revision ID: ac7556d5370e
Revises: eab42bc74d0b
Create Date: 2026-08-18 16:42:09.988063

Reine Daten-Migration: fügt die Singleton-Zeile in filter_rules ein,
die vorher aus data/filter_rules.yaml gelesen wurde. Nach dieser
Revision ist die YAML-Datei zur Laufzeit obsolet — load_filter_rules()
liest jetzt aus der DB (siehe src/agent/filters.py).

Warum die Werte hier hardcodiert stehen und nicht aus der YAML
gelesen werden: eine Alembic-Migration muss reproduzierbar über die
Lebenszeit des Repos laufen. Würden wir zur Laufzeit die YAML lesen,
wäre die Migration abhängig vom Zustand einer Datei, die sich
zwischen Migration-Erzeugung und Migration-Anwendung ändern kann
(anderer Branch, umbenannt, gelöscht). Hardcodiert = die Migration
beschreibt genau EINEN, festen Anfangszustand.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac7556d5370e'
down_revision: Union[str, Sequence[str], None] = 'eab42bc74d0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kopie der Werte aus data/filter_rules.yaml zum Zeitpunkt dieser
# Migration. Auf Modul-Ebene, damit up- und downgrade dieselbe Quelle
# nutzen und der Wert im Diff sichtbar ist.
_SEED_TITLE_BLACKLIST = [
    "Senior",
    "Lead",
    "Principal",
    "Staff",
    "Head of",
    "Architekt",
    "Consultant",
    "Berater",
    "Werkstudent",
    "Praktikum",
]
_SEED_MAX_EXPERIENCE_YEARS = 3
_SEED_DESCRIPTION_BLACKLIST = [
    "Beratungsprojekte",
    "Kundenprojekte vor Ort",
]


def upgrade() -> None:
    """Fügt die einzige filter_rules-Zeile ein.

    Wir nutzen eine gebundene Tabellen-Definition (statt rohem SQL),
    damit die JSON-Serialisierung der Listen von SQLAlchemy übernommen
    wird — sonst müssten wir hier per Hand JSON-Strings zusammenbauen.
    """
    filter_rules_tabelle = sa.table(
        "filter_rules",
        sa.column("title_blacklist", sa.JSON()),
        sa.column("max_experience_years", sa.Integer()),
        sa.column("description_blacklist", sa.JSON()),
    )
    op.bulk_insert(
        filter_rules_tabelle,
        [
            {
                "title_blacklist": _SEED_TITLE_BLACKLIST,
                "max_experience_years": _SEED_MAX_EXPERIENCE_YEARS,
                "description_blacklist": _SEED_DESCRIPTION_BLACKLIST,
            }
        ],
    )


def downgrade() -> None:
    """Löscht die (einzige) filter_rules-Zeile komplett, unabhängig davon,
        ob sie seitdem über die API verändert wurde. filter_rules ist als
        Singleton gedacht -- es gibt nie mehr als eine Zeile, ein bedingtes
        DELETE nur auf Seed-Werte würde nur teilweisen, irreführenden Schutz
        vor Nutzer-Änderungen bieten (z.B. falls nur title_blacklist geändert
        wurde, max_experience_years aber beim Seed-Wert blieb). Ehrliche,
        einfache Semantik: downgrade entfernt alles, was diese Migration
        eingeführt hat.
    """
    op.execute(sa.text("DELETE FROM filter_rules"))

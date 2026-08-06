"""Tests für den pgvector-Query-Mechanismus.

Bewusste Trennung zu test_embeddings.py: hier läuft eine ECHTE Postgres-
Verbindung (db_session-Fixture aus conftest.py), aber KEIN echtes
Embedding-Modell. Die Vektoren werden manuell konstruiert, damit wir
den Query-Mechanismus (cosine_distance auf der Vector-Spalte) isoliert
prüfen — unabhängig davon, ob BAAI/bge-small-en-v1.5 gerade sinnvolle
Embeddings liefert.

Voraussetzungen wie in test_db_models.py: laufender Postgres mit
aktivierter pgvector-Extension unter settings.database_url.
"""

from sqlalchemy.orm import Session

from src.db.models import JobORM

# Dimension der embedding-Spalte in models.py (Vector(384)) — muss
# exakt passen, sonst wirft Postgres beim INSERT einen Dimensionsfehler
EMBEDDING_DIM = 384


def _padded_vektor(prefix: list[float]) -> list[float]:
    """Füllt einen kurzen Prefix-Vektor mit Nullen auf 384 Dimensionen.

    Wir wollen für die Tests nur die ersten paar Dimensionen konstruieren
    (das reicht, um Ähnlichkeit vs. Unähnlichkeit zu modellieren) — den
    Rest mit 0.0 aufzufüllen ist der einfachste Weg, die Vector(384)-
    Spalte zu befriedigen, ohne das Test-Setup unlesbar zu machen.
    """
    return prefix + [0.0] * (EMBEDDING_DIM - len(prefix))


def _make_job(external_id: str, embedding: list[float]) -> JobORM:
    """Fabrik für einen JobORM mit gefüllten Pflichtfeldern + Embedding."""
    return JobORM(
        external_id=external_id,
        title=f"Titel {external_id}",
        company="ACME GmbH",
        location="Hamburg",
        job_url=f"https://example.com/{external_id}",
        description="Dummy-Beschreibung.",
        is_remote=False,
        site="indeed",
        embedding=embedding,
    )


def test_cosine_distance_findet_konstruiert_aehnlichen_vektor(
    db_session: Session,
) -> None:
    """cosine_distance() muss den konstruiert-ähnlichen Vektor als
    nächsten Nachbarn liefern, nicht den konstruiert-unähnlichen.

    Konstruktion:
    - referenz:  [1.0, 0.0, 0.0, ...]  (Einheitsvektor auf Achse 0)
    - aehnlich:  [0.9, 0.1, 0.0, ...]  (fast gleiche Richtung, kleiner Winkel)
    - unaehnlich:[0.0, 1.0, 0.0, ...]  (senkrechte Richtung, Winkel 90°)

    Erwartung:
    - Cosine-Distanz(referenz, aehnlich)   ~ nahe 0  (kleiner Winkel)
    - Cosine-Distanz(referenz, unaehnlich) = 1.0     (Winkel 90°)
    Also muss "aehnlich" vor "unaehnlich" in der sortierten Liste stehen.
    """
    referenz_vektor = _padded_vektor([1.0, 0.0, 0.0])
    aehnlich_vektor = _padded_vektor([0.9, 0.1, 0.0])
    unaehnlich_vektor = _padded_vektor([0.0, 1.0, 0.0])

    db_session.add_all([
        _make_job("pgv-referenz", referenz_vektor),
        _make_job("pgv-aehnlich", aehnlich_vektor),
        _make_job("pgv-unaehnlich", unaehnlich_vektor),
    ])
    db_session.commit()

    # Query: alle drei Jobs nach Distanz zum Referenz-Vektor sortieren.
    # cosine_distance ist die pgvector-SQLAlchemy-Methode direkt auf der
    # Vector-Spalte — sie generiert unter der Haube den <=> Operator.
    ergebnisse = (
        db_session.query(
            JobORM.external_id,
            JobORM.embedding.cosine_distance(referenz_vektor).label("distanz"),
        )
        .filter(JobORM.external_id.like("pgv-%"))
        .order_by("distanz")
        .all()
    )

    ids_sortiert = [external_id for external_id, _ in ergebnisse]
    distanzen = {external_id: distanz for external_id, distanz in ergebnisse}

    # Referenz zu sich selbst: Distanz exakt 0 (bis auf Fließkomma-Rauschen)
    assert distanzen["pgv-referenz"] == 0.0 or distanzen["pgv-referenz"] < 1e-6
    # aehnlich muss näher sein als unaehnlich — Kernaussage des Tests
    assert distanzen["pgv-aehnlich"] < distanzen["pgv-unaehnlich"]
    # Reihenfolge: Referenz (0), aehnlich (klein), unaehnlich (~1.0)
    assert ids_sortiert == ["pgv-referenz", "pgv-aehnlich", "pgv-unaehnlich"]

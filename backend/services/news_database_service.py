"""External news-intelligence PostgreSQL connection.

This service keeps the Docker/news-engine database separate from the main
identity database. The news query methods are inherited from DatabaseService
because the dashboard already expects the same clusters, articles,
cluster_entities, and article_entities table shape.
"""

import psycopg2

try:
    from ..config import settings
    from .database_service import DatabaseService
except ImportError:
    from config import settings
    from services.database_service import DatabaseService

from utils.logger import get_logger


logger = get_logger("identity-search-service.news-database")


class NewsDatabaseService(DatabaseService):
    """Read news intelligence data from the external Docker PostgreSQL DB."""

    def __init__(self):
        """Open the configured external news database without touching identity schema."""

        dsn = self.normalized_dsn()

        if not dsn:

            raise ValueError("NEWS_DATABASE_URL is not configured")

        self.connection = psycopg2.connect(
            dsn,
            connect_timeout=3
        )
        self.cursor = self.connection.cursor()
        self.extended_document_columns = []
        self._prepare_compatibility_views()

    def _prepare_compatibility_views(self):
        """Expose optional news columns expected by dashboard queries per connection."""

        self.cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = %s
            AND column_name = %s
            """,
            (
                "public",
                "cluster_entities",
                "frequency"
            )
        )

        if self.cursor.fetchone():

            return

        self.cursor.execute(
            """
            CREATE TEMP VIEW cluster_entities AS
            SELECT
                id,
                cluster_id,
                entity_type,
                entity_name,
                1::INTEGER AS frequency
            FROM public.cluster_entities
            """
        )
        self.cursor.execute("SET search_path TO pg_temp, public")
        logger.info(
            "External news DB compatibility view enabled: cluster_entities.frequency defaults to 1"
        )

    def get_data_snapshot(self):
        """Return lightweight totals and timestamps after a scraper batch commits."""

        self.cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM clusters),
                (SELECT COUNT(*) FROM articles),
                (SELECT COUNT(*) FROM cluster_entities),
                (SELECT COUNT(*) FROM article_entities),
                (SELECT MAX(updated_at) FROM clusters),
                (SELECT MAX(published_at) FROM articles)
            """
        )
        row = self.cursor.fetchone()

        return {
            "clusters": row[0],
            "articles": row[1],
            "cluster_entities": row[2],
            "article_entities": row[3],
            "latest_cluster_update": row[4].isoformat() if row[4] else None,
            "latest_article_published": row[5].isoformat() if row[5] else None
        }

    @classmethod
    def is_configured(cls):
        """Return true when an external news database DSN is available."""

        return bool(cls.normalized_dsn())

    @staticmethod
    def normalized_dsn():
        """Convert common SQLAlchemy async DSNs into a psycopg2-compatible URL."""

        dsn = str(settings.NEWS_DATABASE_URL or "").strip()

        if dsn.startswith("postgresql+asyncpg://"):

            dsn = dsn.replace(
                "postgresql+asyncpg://",
                "postgresql://",
                1
            )

        return dsn
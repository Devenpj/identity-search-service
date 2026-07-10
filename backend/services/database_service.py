"""PostgreSQL data access coordinator for identity, OSINT, news, and job repositories."""

import psycopg2
import threading

try:
    from services.database_mixins import AsyncJobLifecycleMixin
    from services.identity_repository import IdentityRepositoryMixin
    from services.job_repository import JobRepositoryMixin
    from services.news_repository import NewsRepositoryMixin
    from services.osint_repository import OSINTRepositoryMixin
except ModuleNotFoundError:
    from backend.services.database_mixins import AsyncJobLifecycleMixin
    from backend.services.identity_repository import IdentityRepositoryMixin
    from backend.services.job_repository import JobRepositoryMixin
    from backend.services.news_repository import NewsRepositoryMixin
    from backend.services.osint_repository import OSINTRepositoryMixin


class DatabaseService(
    IdentityRepositoryMixin,
    JobRepositoryMixin,
    OSINTRepositoryMixin,
    NewsRepositoryMixin,
    AsyncJobLifecycleMixin
):
    """Open the database connection and compose focused repository mixins."""

    _schema_ready = False
    _schema_lock = threading.Lock()

    def __init__(self):
        """Open the `excel_import` database and ensure required helper tables."""

        self.connection = psycopg2.connect(
            host="localhost",
            database="excel_import",
            user="postgres",
            password="postgres",
            port="5432"
        )

        self.cursor = self.connection.cursor()
        self._ensure_runtime_schema()
        self.extended_document_columns = self._get_existing_extended_columns()

    def _ensure_runtime_schema(self):
        """Run one-time schema setup lazily instead of on every DB connection."""

        if DatabaseService._schema_ready:

            return

        with DatabaseService._schema_lock:

            if DatabaseService._schema_ready:

                return

            self._ensure_document_columns()
            self._ensure_manual_review_table()
            self._ensure_osint_jobs_table()
            self._ensure_face_search_jobs_table()
            self._ensure_video_face_search_tables()
            self._ensure_face_embeddings_table()
            self._ensure_document_validation_jobs_table()
            self._ensure_osint_normalized_tables()
            self._ensure_news_ingestion_events_table()
            DatabaseService._schema_ready = True

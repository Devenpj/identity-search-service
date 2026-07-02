"""PostgreSQL data access layer for identity, OSINT, and review workflows."""

import psycopg2
from psycopg2 import errors
import json
import re
import threading

from utils.logger import get_logger


logger = get_logger("identity-search-service.database")


class DatabaseService:
    """Own all direct SQL used by the FastAPI backend."""

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
            self._ensure_document_validation_jobs_table()
            self._ensure_osint_normalized_tables()
            self._ensure_news_ingestion_events_table()
            DatabaseService._schema_ready = True

    def _ensure_news_ingestion_events_table(self):
        """Create the idempotent audit table for news-engine webhook batches."""

        query = """
        CREATE TABLE IF NOT EXISTS news_ingestion_events (
            batch_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'news-intelligence-engine',
            reported_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
            database_snapshot JSONB,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT,
            engine_completed_at TIMESTAMPTZ,
            received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT news_ingestion_events_status_check
                CHECK (status IN ('COMPLETED', 'FAILED'))
        );

        CREATE INDEX IF NOT EXISTS idx_news_ingestion_events_received_at
        ON news_ingestion_events(received_at DESC);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_manual_review_table(self):
        """Create the manual review queue table used by reviewer workflows."""

        query = """
        CREATE TABLE IF NOT EXISTS manual_review_cases (
            id SERIAL PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            document_type TEXT,
            employee_id TEXT,
            full_name TEXT,
            uploaded_document_path TEXT,
            extracted_data TEXT,
            database_match TEXT,
            face_result TEXT,
            decision TEXT,
            reviewer_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_osint_jobs_table(self):
        """Create or migrate the OSINT job table to the single JOB00001 ID model."""

        query = """
        CREATE SEQUENCE IF NOT EXISTS osint_job_number_seq START 1;

        CREATE TABLE IF NOT EXISTS osint_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            targets JSONB NOT NULL DEFAULT '[]'::jsonb,
            provider_response JSONB,
            result JSONB,
            result_payload JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submitted_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'osint_jobs'
                AND column_name = 'job_id'
            )
            AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'osint_jobs'
                AND column_name = 'local_job_id'
            ) THEN
                ALTER TABLE osint_jobs RENAME COLUMN local_job_id TO job_id;
            END IF;
        END $$;

        ALTER TABLE osint_jobs
        ADD COLUMN IF NOT EXISTS job_id TEXT;

        ALTER TABLE osint_jobs
        ADD COLUMN IF NOT EXISTS result JSONB;

        ALTER TABLE osint_jobs
        ADD COLUMN IF NOT EXISTS result_payload JSONB;

        UPDATE osint_jobs
        SET result = result_payload
        WHERE result IS NULL
        AND result_payload IS NOT NULL;

        UPDATE osint_jobs
        SET job_id = 'JOB' || LPAD(nextval('osint_job_number_seq')::TEXT, 5, '0')
        WHERE job_id IS NULL
        OR TRIM(job_id) = '';

        ALTER TABLE osint_jobs
        ALTER COLUMN job_id SET NOT NULL;

        ALTER TABLE osint_jobs
        DROP COLUMN IF EXISTS external_job_id;

        ALTER TABLE osint_jobs
        DROP COLUMN IF EXISTS id CASCADE;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_name = 'osint_jobs'
                AND constraint_type = 'PRIMARY KEY'
            ) THEN
                ALTER TABLE osint_jobs ADD PRIMARY KEY (job_id);
            END IF;
        END $$;

        ALTER TABLE osint_jobs
        ALTER COLUMN status SET DEFAULT 'PENDING'
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_face_search_jobs_table(self):
        """Create the persisted face-search job table used for async polling."""

        query = """
        CREATE SEQUENCE IF NOT EXISTS face_search_job_number_seq START 1;

        CREATE TABLE IF NOT EXISTS face_search_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            uploaded_image_path TEXT NOT NULL,
            total_candidates INTEGER,
            progress_percent INTEGER NOT NULL DEFAULT 5,
            progress_message TEXT,
            result JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS total_candidates INTEGER;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 5;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS progress_message TEXT;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS result JSONB;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS error_message TEXT;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

        CREATE INDEX IF NOT EXISTS idx_face_search_jobs_status
        ON face_search_jobs(status);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_document_validation_jobs_table(self):
        """Create the persisted document-validation job table for async polling."""

        query = """
        CREATE SEQUENCE IF NOT EXISTS document_validation_job_number_seq START 1;

        CREATE TABLE IF NOT EXISTS document_validation_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            document_type TEXT NOT NULL,
            uploaded_document_path TEXT NOT NULL,
            original_filename TEXT,
            manual_values JSONB NOT NULL DEFAULT '{}'::jsonb,
            progress_percent INTEGER NOT NULL DEFAULT 5,
            progress_message TEXT,
            result JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS original_filename TEXT;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS manual_values JSONB NOT NULL DEFAULT '{}'::jsonb;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 5;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS progress_message TEXT;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS result JSONB;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS error_message TEXT;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

        CREATE INDEX IF NOT EXISTS idx_document_validation_jobs_status
        ON document_validation_jobs(status);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_osint_normalized_tables(self):
        """Create searchable OSINT tables derived from raw provider payloads."""

        query = """
        CREATE TABLE IF NOT EXISTS osint_profiles (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            platform TEXT,
            target TEXT,
            username TEXT,
            full_name TEXT,
            profile_url TEXT,
            avatar_url TEXT,
            avatar_path TEXT,
            bio TEXT,
            status TEXT,
            confidence TEXT,
            extracted_text TEXT,
            raw_payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_profiles_job_id
        ON osint_profiles(job_id);

        CREATE INDEX IF NOT EXISTS idx_osint_profiles_employee_id
        ON osint_profiles(employee_id);

        CREATE INDEX IF NOT EXISTS idx_osint_profiles_platform
        ON osint_profiles(platform);

        CREATE TABLE IF NOT EXISTS osint_contacts (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            contact_type TEXT,
            target TEXT,
            platform TEXT,
            status TEXT,
            category TEXT,
            details TEXT,
            raw_payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_contacts_job_id
        ON osint_contacts(job_id);

        CREATE INDEX IF NOT EXISTS idx_osint_contacts_target
        ON osint_contacts(target);

        CREATE TABLE IF NOT EXISTS osint_matches (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            platform TEXT,
            url TEXT,
            bio TEXT,
            avatar_url TEXT,
            avatar_path TEXT,
            confidence TEXT,
            raw_payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_matches_job_id
        ON osint_matches(job_id);

        CREATE TABLE IF NOT EXISTS osint_identity_links (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            link_reason TEXT,
            match_score NUMERIC,
            face_match_status TEXT,
            face_score NUMERIC,
            decision TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_identity_links_job_id
        ON osint_identity_links(job_id);

        CREATE INDEX IF NOT EXISTS idx_osint_identity_links_employee_id
        ON osint_identity_links(employee_id);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _get_existing_extended_columns(self):
        """Detect optional document columns so old databases still work."""

        query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'demodataset'
        AND column_name IN (
            'voter_id_number',
            'driving_license_number',
            'passport_number'
        )
        """

        self.cursor.execute(query)

        return {
            row[0]
            for row in self.cursor.fetchall()
        }

    def _ensure_document_columns(self):
        """Add optional document-number columns used by extended ID types."""

        query = """
        ALTER TABLE demodataset
        ADD COLUMN IF NOT EXISTS voter_id_number TEXT,
        ADD COLUMN IF NOT EXISTS driving_license_number TEXT,
        ADD COLUMN IF NOT EXISTS passport_number TEXT
        """

        try:

            self.cursor.execute("SET lock_timeout TO '2s'")
            self.cursor.execute(query)
            self.connection.commit()

        except errors.LockNotAvailable:

            self.connection.rollback()

    # -----------------------------------
    # DYNAMIC SEARCH
    # -----------------------------------

    def search_identity(
        self,
        field,
        value
    ):
        """Search `demodataset` by one allowed field and return profile rows."""

        condition = self._build_search_condition(
            field,
            value
        )

        if not condition:

            return []

        where_clause, parameter = condition

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE {where_clause}
        LIMIT 20
        """

        self.cursor.execute(
            query,
            self._condition_parameters(parameter)
        )

        results = self.cursor.fetchall()

        return [
            self._format_identity_row(row)
            for row in results
        ]

    def search_identity_multi(
        self,
        criteria
    ):
        """Search `demodataset` using all provided criteria together."""

        conditions = []
        parameters = []

        for item in criteria or []:

            condition = self._build_search_condition(
                item.get("field"),
                item.get("value")
            )

            if not condition:

                continue

            where_clause, parameter = condition
            conditions.append(where_clause)
            parameters.extend(
                self._condition_parameters(parameter)
            )

        if not conditions:

            return []

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE {" AND ".join(f"({condition})" for condition in conditions)}
        LIMIT 50
        """

        self.cursor.execute(
            query,
            tuple(parameters)
        )

        formatted_results = [
            self._format_identity_row(row)
            for row in self.cursor.fetchall()
        ]

        for result in formatted_results:

            result["_matched_fields"] = self._matched_fields_for_identity(
                result,
                criteria
            )

        return formatted_results

    # -----------------------------------
    # OSINT JOBS
    # -----------------------------------

    def _next_face_search_job_id(self):
        """Generate the next readable async face-search job ID like FACE00001."""

        self.cursor.execute(
            """
            SELECT 'FACE' || LPAD(nextval('face_search_job_number_seq')::TEXT, 5, '0')
            """
        )

        return self.cursor.fetchone()[0]

    def create_face_search_job(
        self,
        uploaded_image_path
    ):
        """Insert a pending face-search job and return the stored job payload."""

        job_id = self._next_face_search_job_id()
        query = """
        INSERT INTO face_search_jobs (
            job_id,
            status,
            uploaded_image_path,
            progress_percent,
            progress_message
        )
        VALUES (%s, 'PENDING', %s, 10, 'Face image uploaded. Waiting to start search.')
        RETURNING
            job_id,
            status,
            uploaded_image_path,
            total_candidates,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                job_id,
                uploaded_image_path
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_face_search_job_row(row)

        logger.info(
            "Face search DB state: job_id=%s status=PENDING uploaded_image_path=%s",
            job_id,
            uploaded_image_path
        )

        return formatted_job

    def mark_face_search_job_processing(
        self,
        job_id,
        total_candidates
    ):
        """Move a face-search job into processing after candidates are loaded."""

        query = """
        UPDATE face_search_jobs
        SET
            status = 'PROCESSING',
            total_candidates = %s,
            progress_percent = 35,
            progress_message = 'Database face candidates loaded. Comparing faces now.',
            error_message = NULL,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(
            query,
            (
                total_candidates,
                job_id
            )
        )
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.info(
                "Face search DB state: job_id=%s status=PROCESSING total_candidates=%s",
                job_id,
                total_candidates
            )
        else:
            logger.error(
                "Face search DB state update failed: job_id=%s status=PROCESSING reason=job_not_found",
                job_id
            )

    def complete_face_search_job(
        self,
        job_id,
        result_payload,
        total_candidates
    ):
        """Persist a completed face-search result for polling and later display."""

        serialized_payload = json.dumps(result_payload or {})
        query = """
        UPDATE face_search_jobs
        SET
            status = 'COMPLETED',
            total_candidates = %s,
            progress_percent = 100,
            progress_message = 'Face search completed.',
            result = %s::jsonb,
            error_message = NULL,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        RETURNING
            job_id,
            status,
            uploaded_image_path,
            total_candidates,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                total_candidates,
                serialized_payload,
                job_id
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_face_search_job_row(row)

        if formatted_job:
            logger.info(
                "Face search DB state: job_id=%s status=COMPLETED matched=%s best_score=%s",
                job_id,
                formatted_job.get("matched"),
                formatted_job.get("best_score")
            )
        else:
            logger.error(
                "Face search DB complete failed: job_id=%s reason=job_not_found",
                job_id
            )

        return formatted_job

    def mark_face_search_job_failed(
        self,
        job_id,
        error_message
    ):
        """Persist a failed face-search state and its error message."""

        query = """
        UPDATE face_search_jobs
        SET
            status = 'FAILED',
            progress_percent = 100,
            progress_message = 'Face search failed.',
            error_message = %s,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        normalized_error = str(error_message or "Unknown face search error")
        self.cursor.execute(
            query,
            (
                normalized_error,
                job_id
            )
        )
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.error(
                "Face search DB state: job_id=%s status=FAILED error=%s",
                job_id,
                normalized_error
            )
        else:
            logger.error(
                "Face search DB state update failed: job_id=%s status=FAILED reason=job_not_found error=%s",
                job_id,
                normalized_error
            )

    def update_face_search_job_progress(
        self,
        job_id,
        progress_percent,
        progress_message
    ):
        """Update visible face-search progress for dashboard polling."""

        query = """
        UPDATE face_search_jobs
        SET
            progress_percent = %s,
            progress_message = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(
            query,
            (
                int(progress_percent),
                str(progress_message or ""),
                job_id
            )
        )
        self.connection.commit()

    def mark_stale_face_search_jobs_failed(
        self,
        max_age_minutes=30
    ):
        """Fail face-search jobs that exceeded the allowed processing window."""

        try:
            stale_minutes = max(
                1,
                int(max_age_minutes or 30)
            )
        except (TypeError, ValueError):
            stale_minutes = 30

        error_message = (
            "Face search job timed out before completion. "
            f"No final result was saved within {stale_minutes} minutes. "
            "Likely causes: face engine stopped, backend restarted, network timeout, "
            "or a long-running comparison failure."
        )
        query = """
        UPDATE face_search_jobs
        SET
            status = 'FAILED',
            progress_percent = 100,
            progress_message = 'Face search timed out.',
            error_message = %s,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE status IN ('PENDING', 'PROCESSING')
        AND COALESCE(started_at, created_at) < (
            CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
        )
        RETURNING job_id
        """

        self.cursor.execute(
            query,
            (
                error_message,
                stale_minutes
            )
        )
        rows = self.cursor.fetchall()
        self.connection.commit()
        expired_job_ids = [
            row[0]
            for row in rows
        ]

        if expired_job_ids:
            logger.error(
                "Face search stale jobs marked failed: count=%s max_age_minutes=%s job_ids=%s",
                len(expired_job_ids),
                stale_minutes,
                expired_job_ids
            )

        return expired_job_ids

    def get_face_search_job(
        self,
        job_id
    ):
        """Fetch one face-search job for dashboard polling and final display."""

        query = """
        SELECT
            job_id,
            status,
            uploaded_image_path,
            total_candidates,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        FROM face_search_jobs
        WHERE job_id = %s
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (job_id,)
        )

        return self._format_face_search_job_row(
            self.cursor.fetchone()
        )

    def _next_document_validation_job_id(self):
        """Generate the next readable document-validation job ID like DOC00001."""

        self.cursor.execute(
            """
            SELECT 'DOC' || LPAD(nextval('document_validation_job_number_seq')::TEXT, 5, '0')
            """
        )

        return self.cursor.fetchone()[0]

    def create_document_validation_job(
        self,
        document_type,
        uploaded_document_path,
        original_filename,
        manual_values
    ):
        """Insert a pending document-validation job and return its payload."""

        job_id = self._next_document_validation_job_id()
        query = """
        INSERT INTO document_validation_jobs (
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message
        )
        VALUES (%s, 'PENDING', %s, %s, %s, %s::jsonb, 10, 'Document uploaded. Waiting to start validation.')
        RETURNING
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                job_id,
                document_type,
                uploaded_document_path,
                original_filename,
                json.dumps(manual_values or {})
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_document_validation_job_row(row)

        logger.info(
            "Document validation DB state: job_id=%s status=PENDING document_type=%s path=%s",
            job_id,
            document_type,
            uploaded_document_path
        )

        return formatted_job

    def mark_document_validation_job_processing(
        self,
        job_id
    ):
        """Move a document-validation job into processing."""

        query = """
        UPDATE document_validation_jobs
        SET
            status = 'PROCESSING',
            progress_percent = 30,
            progress_message = 'Document validation started. Checking document type and OCR.',
            error_message = NULL,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(query, (job_id,))
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.info(
                "Document validation DB state: job_id=%s status=PROCESSING",
                job_id
            )
        else:
            logger.error(
                "Document validation DB state update failed: job_id=%s status=PROCESSING reason=job_not_found",
                job_id
            )

    def complete_document_validation_job(
        self,
        job_id,
        result_payload
    ):
        """Persist a completed document-validation result for polling/display."""

        serialized_payload = json.dumps(result_payload or {})
        query = """
        UPDATE document_validation_jobs
        SET
            status = 'COMPLETED',
            progress_percent = 100,
            progress_message = 'Document validation completed.',
            result = %s::jsonb,
            error_message = NULL,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        RETURNING
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                serialized_payload,
                job_id
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_document_validation_job_row(row)

        if formatted_job:
            decision = (formatted_job.get("result") or {}).get("decision") or {}
            logger.info(
                "Document validation DB state: job_id=%s status=COMPLETED decision=%s",
                job_id,
                decision.get("status")
            )
        else:
            logger.error(
                "Document validation DB complete failed: job_id=%s reason=job_not_found",
                job_id
            )

        return formatted_job

    def mark_document_validation_job_failed(
        self,
        job_id,
        error_message
    ):
        """Persist a failed document-validation state and its error message."""

        query = """
        UPDATE document_validation_jobs
        SET
            status = 'FAILED',
            progress_percent = 100,
            progress_message = 'Document validation failed.',
            error_message = %s,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        normalized_error = str(error_message or "Unknown document validation error")
        self.cursor.execute(
            query,
            (
                normalized_error,
                job_id
            )
        )
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.error(
                "Document validation DB state: job_id=%s status=FAILED error=%s",
                job_id,
                normalized_error
            )
        else:
            logger.error(
                "Document validation DB state update failed: job_id=%s status=FAILED reason=job_not_found error=%s",
                job_id,
                normalized_error
            )

    def update_document_validation_job_progress(
        self,
        job_id,
        progress_percent,
        progress_message
    ):
        """Update visible document-validation progress for dashboard polling."""

        query = """
        UPDATE document_validation_jobs
        SET
            progress_percent = %s,
            progress_message = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(
            query,
            (
                int(progress_percent),
                str(progress_message or ""),
                job_id
            )
        )
        self.connection.commit()

    def mark_stale_document_validation_jobs_failed(
        self,
        max_age_minutes=30
    ):
        """Fail document-validation jobs that exceeded the allowed processing window."""

        try:
            stale_minutes = max(1, int(max_age_minutes or 30))
        except (TypeError, ValueError):
            stale_minutes = 30

        error_message = (
            "Document validation job timed out before completion. "
            f"No final result was saved within {stale_minutes} minutes. "
            "Likely causes: OCR process stopped, backend restarted, or a long-running verification failure."
        )
        query = """
        UPDATE document_validation_jobs
        SET
            status = 'FAILED',
            progress_percent = 100,
            progress_message = 'Document validation timed out.',
            error_message = %s,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE status IN ('PENDING', 'PROCESSING')
        AND COALESCE(started_at, created_at) < (
            CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
        )
        RETURNING job_id
        """

        self.cursor.execute(
            query,
            (
                error_message,
                stale_minutes
            )
        )
        rows = self.cursor.fetchall()
        self.connection.commit()
        expired_job_ids = [row[0] for row in rows]

        if expired_job_ids:
            logger.error(
                "Document validation stale jobs marked failed: count=%s max_age_minutes=%s job_ids=%s",
                len(expired_job_ids),
                stale_minutes,
                expired_job_ids
            )

        return expired_job_ids

    def get_document_validation_job(
        self,
        job_id
    ):
        """Fetch one document-validation job for dashboard polling and display."""

        query = """
        SELECT
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        FROM document_validation_jobs
        WHERE job_id = %s
        LIMIT 1
        """

        self.cursor.execute(query, (job_id,))

        return self._format_document_validation_job_row(
            self.cursor.fetchone()
        )
    def create_osint_job(
        self,
        targets,
        job_id=None
    ):
        """Insert a pending OSINT job and return the stored job payload."""

        if not job_id:

            job_id = self._next_osint_job_id()

        query = """
        INSERT INTO osint_jobs (
            job_id,
            status,
            targets
        )
        VALUES (%s, 'PENDING', %s::jsonb)
        RETURNING
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                job_id,
                json.dumps(targets)
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_osint_job_row(row)

        if not formatted_job or not formatted_job.get("job_id"):
            logger.error(
                "OSINT DB insert verification failed: job_id=%s reason=missing_returned_row",
                job_id
            )
            raise ValueError("OSINT job could not be saved in the database")

        persisted_job = self.get_osint_job(
            formatted_job.get("job_id")
        )

        if not persisted_job:
            logger.error(
                "OSINT DB insert verification failed: job_id=%s reason=post_commit_lookup_missing",
                formatted_job.get("job_id")
            )
            raise ValueError("OSINT job was not visible in the database after creation")

        logger.info(
            "OSINT DB state: job_id=%s status=PENDING targets=%s persisted=True",
            formatted_job.get("job_id"),
            len(targets or [])
        )

        return persisted_job

    def _next_osint_job_id(self):
        """Generate the next human-readable OSINT job ID like JOB00001."""

        query = """
        SELECT 'JOB' || LPAD(nextval('osint_job_number_seq')::TEXT, 5, '0')
        """

        self.cursor.execute(query)

        return self.cursor.fetchone()[0]

    def mark_osint_job_submitted(
        self,
        job_id,
        provider_response
    ):
        """Move an OSINT job from PENDING to PROCESSING after provider accepts it."""

        query = """
        UPDATE osint_jobs
        SET
            status = 'PROCESSING',
            provider_response = %s::jsonb,
            error_message = NULL,
            submitted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(
            query,
            (
                json.dumps(provider_response),
                job_id
            )
        )
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.info(
                "OSINT DB state: job_id=%s status=PROCESSING provider_response_saved=True",
                job_id
            )
        else:
            logger.error(
                "OSINT DB state update failed: job_id=%s status=PROCESSING reason=job_not_found",
                job_id
            )

    def mark_osint_job_failed(
        self,
        job_id,
        error_message
    ):
        """Persist a failed OSINT state and its error message."""

        query = """
        UPDATE osint_jobs
        SET
            status = 'FAILED',
            error_message = %s,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(
            query,
            (
                str(error_message or "Unknown OSINT error"),
                job_id
            )
        )
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.error(
                "OSINT DB state: job_id=%s status=FAILED error=%s",
                job_id,
                str(error_message or "Unknown OSINT error")
            )
        else:
            logger.error(
                "OSINT DB state update failed: job_id=%s status=FAILED reason=job_not_found error=%s",
                job_id,
                str(error_message or "Unknown OSINT error")
            )

    def mark_stale_osint_jobs_failed(
        self,
        max_age_minutes=15
    ):
        """Fail OSINT jobs that exceeded the allowed processing window."""

        try:
            stale_minutes = max(
                1,
                int(max_age_minutes or 15)
            )
        except (TypeError, ValueError):
            stale_minutes = 15

        error_message = (
            "OSINT job timed out before completion. "
            f"No completed webhook was received within {stale_minutes} minutes. "
            "Likely causes: OSINT engine stopped, callback URL unreachable, "
            "network/firewall issue, or provider processing failure."
        )
        query = """
        UPDATE osint_jobs
        SET
            status = 'FAILED',
            error_message = %s,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE status IN ('PENDING', 'PROCESSING')
        AND COALESCE(submitted_at, created_at) < (
            CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
        )
        RETURNING job_id
        """

        self.cursor.execute(
            query,
            (
                error_message,
                stale_minutes
            )
        )
        rows = self.cursor.fetchall()
        self.connection.commit()
        expired_job_ids = [
            row[0]
            for row in rows
        ]

        if expired_job_ids:
            logger.error(
                "OSINT stale jobs marked failed: count=%s max_age_minutes=%s job_ids=%s",
                len(expired_job_ids),
                stale_minutes,
                expired_job_ids
            )

        return expired_job_ids

    def complete_osint_job(
        self,
        job_id,
        status,
        result_payload
    ):
        """Store a webhook payload and mark the OSINT job terminal/non-terminal."""

        normalized_status = str(status or "COMPLETED").strip().upper()

        if normalized_status not in {
            "COMPLETED",
            "FAILED",
            "PROCESSING",
            "PENDING"
        }:

            normalized_status = "COMPLETED"

        query = """
        UPDATE osint_jobs
        SET
            status = %s,
            result = %s::jsonb,
            result_payload = %s::jsonb,
            error_message = CASE
                WHEN %s = 'FAILED'
                THEN COALESCE(%s::jsonb ->> 'message', 'OSINT provider reported failure')
                ELSE NULL
            END,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        RETURNING
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        """
        serialized_payload = json.dumps(result_payload)

        self.cursor.execute(
            query,
            (
                normalized_status,
                serialized_payload,
                serialized_payload,
                normalized_status,
                serialized_payload,
                job_id
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_osint_job_row(row)

        if formatted_job:
            logger.info(
                "OSINT DB state: job_id=%s status=%s result_saved=%s",
                job_id,
                formatted_job.get("status"),
                formatted_job.get("results") is not None
            )
        else:
            logger.error(
                "OSINT DB complete failed: job_id=%s reason=job_not_found",
                job_id
            )

        return formatted_job

    def find_latest_osint_job_by_targets(
        self,
        target_values
    ):
        """Find the newest active OSINT job whose stored targets match payload values."""

        normalized_values = [
            str(value or "").strip().lower()
            for value in target_values or []
            if str(value or "").strip()
        ]

        if not normalized_values:

            return None

        query = """
        SELECT
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        FROM osint_jobs
        WHERE status IN ('PENDING', 'PROCESSING')
        AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements(targets) AS target_item
            WHERE LOWER(target_item ->> 'value') = ANY(%s)
        )
        ORDER BY
            updated_at DESC NULLS LAST,
            created_at DESC NULLS LAST
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (normalized_values,)
        )

        return self._format_osint_job_row(
            self.cursor.fetchone()
        )

    def get_osint_job(
        self,
        job_id
    ):
        """Fetch one OSINT job for dashboard polling/display."""

        query = """
        SELECT
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        FROM osint_jobs
        WHERE job_id = %s
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (job_id,)
        )

        return self._format_osint_job_row(
            self.cursor.fetchone()
        )

    def get_normalized_osint_data(
        self,
        job_id
    ):
        """Return normalized OSINT rows for clean dashboard retrieval."""

        self.cursor.execute(
            """
            SELECT
                platform,
                target,
                username,
                full_name,
                profile_url,
                avatar_url,
                avatar_path,
                bio,
                status,
                confidence,
                extracted_text
            FROM osint_profiles
            WHERE job_id = %s
            ORDER BY id
            """,
            (job_id,)
        )
        profiles = [
            {
                "platform": row[0],
                "target": row[1],
                "username": row[2],
                "full_name": row[3],
                "profile_url": row[4],
                "avatar_url": row[5],
                "avatar_path": row[6],
                "bio": row[7],
                "status": row[8],
                "confidence": row[9],
                "extracted_text": row[10]
            }
            for row in self.cursor.fetchall()
        ]

        self.cursor.execute(
            """
            SELECT
                contact_type,
                target,
                platform,
                status,
                category,
                details
            FROM osint_contacts
            WHERE job_id = %s
            ORDER BY id
            """,
            (job_id,)
        )
        contacts = [
            {
                "contact_type": row[0],
                "target": row[1],
                "platform": row[2],
                "status": row[3],
                "category": row[4],
                "details": row[5]
            }
            for row in self.cursor.fetchall()
        ]

        self.cursor.execute(
            """
            SELECT
                platform,
                url,
                bio,
                avatar_url,
                avatar_path,
                confidence
            FROM osint_matches
            WHERE job_id = %s
            ORDER BY id
            """,
            (job_id,)
        )
        matches = [
            {
                "platform": row[0],
                "url": row[1],
                "bio": row[2],
                "avatar_url": row[3],
                "avatar_path": row[4],
                "confidence": row[5]
            }
            for row in self.cursor.fetchall()
        ]

        return {
            "profiles": profiles,
            "contacts": contacts,
            "matches": matches
        }

    def replace_normalized_osint_data(
        self,
        job_id,
        profiles=None,
        contacts=None,
        matches=None,
        identity_links=None
    ):
        """Replace searchable OSINT rows for one job without touching raw JSON."""

        profiles = profiles or []
        contacts = contacts or []
        matches = matches or []
        identity_links = identity_links or []

        try:

            for table_name in (
                "osint_identity_links",
                "osint_matches",
                "osint_contacts",
                "osint_profiles"
            ):

                self.cursor.execute(
                    f"DELETE FROM {table_name} WHERE job_id = %s",
                    (job_id,)
                )

            for profile in profiles:

                self.cursor.execute(
                    """
                    INSERT INTO osint_profiles (
                        job_id,
                        employee_id,
                        platform,
                        target,
                        username,
                        full_name,
                        profile_url,
                        avatar_url,
                        avatar_path,
                        bio,
                        status,
                        confidence,
                        extracted_text,
                        raw_payload
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb
                    )
                    """,
                    (
                        job_id,
                        profile.get("employee_id"),
                        profile.get("platform"),
                        profile.get("target"),
                        profile.get("username"),
                        profile.get("full_name"),
                        profile.get("profile_url"),
                        profile.get("avatar_url"),
                        profile.get("avatar_path"),
                        profile.get("bio"),
                        profile.get("status"),
                        profile.get("confidence"),
                        profile.get("extracted_text"),
                        json.dumps(profile.get("raw_payload") or {})
                    )
                )

            for contact in contacts:

                self.cursor.execute(
                    """
                    INSERT INTO osint_contacts (
                        job_id,
                        employee_id,
                        contact_type,
                        target,
                        platform,
                        status,
                        category,
                        details,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        job_id,
                        contact.get("employee_id"),
                        contact.get("contact_type"),
                        contact.get("target"),
                        contact.get("platform"),
                        contact.get("status"),
                        contact.get("category"),
                        contact.get("details"),
                        json.dumps(contact.get("raw_payload") or {})
                    )
                )

            for match in matches:

                self.cursor.execute(
                    """
                    INSERT INTO osint_matches (
                        job_id,
                        employee_id,
                        platform,
                        url,
                        bio,
                        avatar_url,
                        avatar_path,
                        confidence,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        job_id,
                        match.get("employee_id"),
                        match.get("platform"),
                        match.get("url"),
                        match.get("bio"),
                        match.get("avatar_url"),
                        match.get("avatar_path"),
                        match.get("confidence"),
                        json.dumps(match.get("raw_payload") or {})
                    )
                )

            for identity_link in identity_links:

                self.cursor.execute(
                    """
                    INSERT INTO osint_identity_links (
                        job_id,
                        employee_id,
                        link_reason,
                        match_score,
                        face_match_status,
                        face_score,
                        decision
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        identity_link.get("employee_id"),
                        identity_link.get("link_reason"),
                        identity_link.get("match_score"),
                        identity_link.get("face_match_status"),
                        identity_link.get("face_score"),
                        identity_link.get("decision")
                    )
                )

            self.connection.commit()

            logger.info(
                "OSINT normalized data stored: job_id=%s profiles=%s contacts=%s matches=%s identity_links=%s",
                job_id,
                len(profiles),
                len(contacts),
                len(matches),
                len(identity_links)
            )

        except Exception:

            self.connection.rollback()
            raise

    def _format_osint_job_row(
        self,
        row
    ):
        """Convert an OSINT SQL row into JSON-friendly API shape."""

        if not row:

            return None

        return {
            "job_id": row[0],
            "status": row[1],
            "targets": row[2] or [],
            "provider_response": row[3],
            "results": row[4],
            "error_message": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
            "submitted_at": row[7].isoformat() if row[7] else None,
            "completed_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None
        }

    def _format_document_validation_job_row(
        self,
        row
    ):
        """Convert a document-validation SQL row into dashboard/API shape."""

        if not row:

            return None

        result_payload = row[8] or {}

        return {
            "job_id": row[0],
            "status": row[1],
            "document_type": row[2],
            "uploaded_document_path": row[3],
            "original_filename": row[4],
            "manual_values": row[5] or {},
            "progress_percent": row[6] or 0,
            "progress_message": row[7],
            "result": result_payload,
            "decision": result_payload.get("decision"),
            "extracted_data": result_payload.get("extracted_data"),
            "database_match": result_payload.get("database_match"),
            "face_verification": result_payload.get("face_verification"),
            "risk_assessment": result_payload.get("risk_assessment"),
            "manual_review_case": result_payload.get("manual_review_case"),
            "error_message": row[9],
            "created_at": row[10].isoformat() if row[10] else None,
            "started_at": row[11].isoformat() if row[11] else None,
            "completed_at": row[12].isoformat() if row[12] else None,
            "updated_at": row[13].isoformat() if row[13] else None
        }

    def _format_face_search_job_row(
        self,
        row
    ):
        """Convert a face-search SQL row into the API/dashboard payload shape."""

        if not row:

            return None

        result_payload = row[6] or {}

        return {
            "job_id": row[0],
            "status": row[1],
            "uploaded_image_path": row[2],
            "total_candidates": row[3],
            "progress_percent": row[4] or 0,
            "progress_message": row[5],
            "result": result_payload,
            "matched": result_payload.get("matched"),
            "best_score": result_payload.get("best_score"),
            "database_match": result_payload.get("database_match"),
            "face_verification": result_payload.get("face_verification"),
            "top_candidates": result_payload.get("top_candidates", []),
            "error_message": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "started_at": row[9].isoformat() if row[9] else None,
            "completed_at": row[10].isoformat() if row[10] else None,
            "updated_at": row[11].isoformat() if row[11] else None
        }

    # -----------------------------------
    # NEWS INTELLIGENCE
    # -----------------------------------

    def save_news_ingestion_event(
        self,
        batch_id,
        status,
        payload,
        reported_counts=None,
        database_snapshot=None,
        source="news-intelligence-engine",
        error_message=None,
        engine_completed_at=None
    ):
        """Insert or update one news batch receipt using batch_id idempotency."""

        normalized_status = str(status or "").strip().upper()

        if normalized_status not in {"COMPLETED", "FAILED"}:

            raise ValueError("News batch status must be COMPLETED or FAILED")

        query = """
        INSERT INTO news_ingestion_events (
            batch_id,
            status,
            source,
            reported_counts,
            database_snapshot,
            payload,
            error_message,
            engine_completed_at
        )
        VALUES (
            %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::timestamptz
        )
        ON CONFLICT (batch_id) DO UPDATE
        SET
            status = EXCLUDED.status,
            source = EXCLUDED.source,
            reported_counts = EXCLUDED.reported_counts,
            database_snapshot = EXCLUDED.database_snapshot,
            payload = EXCLUDED.payload,
            error_message = EXCLUDED.error_message,
            engine_completed_at = EXCLUDED.engine_completed_at,
            updated_at = CURRENT_TIMESTAMP
        RETURNING
            batch_id,
            status,
            source,
            reported_counts,
            database_snapshot,
            error_message,
            engine_completed_at,
            received_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                batch_id,
                normalized_status,
                source,
                json.dumps(reported_counts or {}),
                json.dumps(database_snapshot),
                json.dumps(payload or {}),
                error_message,
                engine_completed_at
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()

        return self._format_news_ingestion_event(row)

    def get_latest_news_ingestion_event(self):
        """Return the most recently received news-engine batch notification."""

        self.cursor.execute(
            """
            SELECT
                batch_id,
                status,
                source,
                reported_counts,
                database_snapshot,
                error_message,
                engine_completed_at,
                received_at,
                updated_at
            FROM news_ingestion_events
            ORDER BY received_at DESC
            LIMIT 1
            """
        )

        return self._format_news_ingestion_event(self.cursor.fetchone())

    @staticmethod
    def _format_news_ingestion_event(row):
        """Convert one news batch audit row to a JSON-safe dictionary."""

        if not row:

            return None

        return {
            "batch_id": row[0],
            "status": row[1],
            "source": row[2],
            "reported_counts": row[3] or {},
            "database_snapshot": row[4],
            "error_message": row[5],
            "engine_completed_at": row[6].isoformat() if row[6] else None,
            "received_at": row[7].isoformat() if row[7] else None,
            "updated_at": row[8].isoformat() if row[8] else None
        }

    def list_top_news_clusters(
        self,
        limit=10
    ):
        """Return the highest-volume news clusters with source/entity context."""

        limit = max(
            1,
            min(
                int(limit or 10),
                50
            )
        )
        query = """
        WITH article_counts AS (
            SELECT
                cluster_id,
                COUNT(*) AS actual_article_count
            FROM articles
            GROUP BY cluster_id
        ),
        source_rank AS (
            SELECT
                cluster_id,
                source,
                COUNT(*) AS source_count,
                ROW_NUMBER() OVER (
                    PARTITION BY cluster_id
                    ORDER BY COUNT(*) DESC, source
                ) AS row_number
            FROM articles
            GROUP BY cluster_id, source
        ),
        entity_rank AS (
            SELECT
                cluster_id,
                entity_type,
                entity_name,
                frequency,
                ROW_NUMBER() OVER (
                    PARTITION BY cluster_id
                    ORDER BY frequency DESC, entity_name
                ) AS row_number
            FROM cluster_entities
        ),
        entity_payload AS (
            SELECT
                cluster_id,
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'entity_type', entity_type,
                        'entity_name', entity_name,
                        'frequency', frequency
                    )
                    ORDER BY frequency DESC, entity_name
                ) AS entities
            FROM entity_rank
            WHERE row_number <= 6
            GROUP BY cluster_id
        )
        SELECT
            c.cluster_id,
            c.cluster_name,
            c.cluster_summary,
            c.article_count,
            COALESCE(ac.actual_article_count, 0) AS actual_article_count,
            c.updated_at,
            sr.source AS top_source,
            sr.source_count AS top_source_count,
            COALESCE(ep.entities, '[]'::json) AS entities
        FROM clusters c
        LEFT JOIN article_counts ac ON ac.cluster_id = c.cluster_id
        LEFT JOIN source_rank sr ON sr.cluster_id = c.cluster_id
            AND sr.row_number = 1
        LEFT JOIN entity_payload ep ON ep.cluster_id = c.cluster_id
        WHERE c.cluster_id <> 'UNCATEGORIZED'
        ORDER BY
            COALESCE(ac.actual_article_count, c.article_count, 0) DESC,
            c.updated_at DESC NULLS LAST,
            c.cluster_id
        LIMIT %s
        """

        self.cursor.execute(
            query,
            (limit,)
        )

        return [
            self._format_news_cluster_row(row)
            for row in self.cursor.fetchall()
        ]

    def get_news_cluster_detail(
        self,
        cluster_id
    ):
        """Return one cluster with its source breakdown, entities, and articles."""

        query = """
        WITH article_counts AS (
            SELECT
                cluster_id,
                COUNT(*) AS actual_article_count
            FROM articles
            WHERE cluster_id = %s
            GROUP BY cluster_id
        )
        SELECT
            c.cluster_id,
            c.cluster_name,
            c.cluster_summary,
            c.article_count,
            COALESCE(ac.actual_article_count, 0) AS actual_article_count,
            c.updated_at,
            NULL AS top_source,
            NULL AS top_source_count,
            '[]'::json AS entities
        FROM clusters c
        LEFT JOIN article_counts ac ON ac.cluster_id = c.cluster_id
        WHERE c.cluster_id = %s
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (
                cluster_id,
                cluster_id
            )
        )
        cluster = self._format_news_cluster_row(
            self.cursor.fetchone()
        )

        if not cluster:

            return None

        self.cursor.execute(
            """
            SELECT
                COALESCE(source, 'Unknown') AS source,
                COUNT(*) AS article_count
            FROM articles
            WHERE cluster_id = %s
            GROUP BY COALESCE(source, 'Unknown')
            ORDER BY article_count DESC, source
            """,
            (cluster_id,)
        )
        sources = [
            self._format_news_source_row(row)
            for row in self.cursor.fetchall()
        ]

        self.cursor.execute(
            """
            SELECT
                entity_type,
                entity_name,
                frequency
            FROM cluster_entities
            WHERE cluster_id = %s
            ORDER BY frequency DESC, entity_type, entity_name
            LIMIT 40
            """,
            (cluster_id,)
        )
        entities = [
            self._format_news_entity_row(row)
            for row in self.cursor.fetchall()
        ]

        self.cursor.execute(
            """
            SELECT
                article_id,
                title,
                content,
                source,
                url,
                published_at,
                created_at
            FROM articles
            WHERE cluster_id = %s
            ORDER BY published_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 50
            """,
            (cluster_id,)
        )
        articles = [
            self._format_news_article_row(row)
            for row in self.cursor.fetchall()
        ]

        cluster["sources"] = sources
        cluster["entities"] = entities
        cluster["articles"] = articles

        return cluster

    def search_news(
        self,
        query_text,
        limit=10
    ):
        """Search clusters, articles, and extracted entities for a news topic."""

        query_text = str(query_text or "").strip()

        if not query_text:

            return []

        limit = max(
            1,
            min(
                int(limit or 10),
                50
            )
        )
        pattern = f"%{query_text}%"
        query = """
        WITH search AS (
            SELECT %s::TEXT AS pattern
        ),
        article_counts AS (
            SELECT
                cluster_id,
                COUNT(*) AS actual_article_count
            FROM articles
            GROUP BY cluster_id
        ),
        matched_clusters AS (
            SELECT
                c.cluster_id,
                ARRAY_REMOVE(
                    ARRAY[
                        CASE WHEN c.cluster_name ILIKE s.pattern THEN 'cluster name' END,
                        CASE WHEN c.cluster_summary ILIKE s.pattern THEN 'cluster summary' END,
                        CASE
                            WHEN EXISTS (
                                SELECT 1
                                FROM articles a
                                WHERE a.cluster_id = c.cluster_id
                                AND (
                                    a.title ILIKE s.pattern
                                    OR a.content ILIKE s.pattern
                                )
                            ) THEN 'article text'
                        END,
                        CASE
                            WHEN EXISTS (
                                SELECT 1
                                FROM articles a
                                WHERE a.cluster_id = c.cluster_id
                                AND a.source ILIKE s.pattern
                            ) THEN 'source'
                        END,
                        CASE
                            WHEN EXISTS (
                                SELECT 1
                                FROM cluster_entities ce
                                WHERE ce.cluster_id = c.cluster_id
                                AND ce.entity_name ILIKE s.pattern
                            ) THEN 'cluster entity'
                        END,
                        CASE
                            WHEN EXISTS (
                                SELECT 1
                                FROM articles a
                                JOIN article_entities ae ON ae.article_id = a.article_id
                                WHERE a.cluster_id = c.cluster_id
                                AND ae.entity_name ILIKE s.pattern
                            ) THEN 'article entity'
                        END
                    ],
                    NULL
                ) AS matched_fields,
                (
                    CASE WHEN c.cluster_name ILIKE s.pattern THEN 45 ELSE 0 END
                    + CASE WHEN c.cluster_summary ILIKE s.pattern THEN 20 ELSE 0 END
                    + CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM cluster_entities ce
                            WHERE ce.cluster_id = c.cluster_id
                            AND ce.entity_name ILIKE s.pattern
                        ) THEN 35 ELSE 0
                    END
                    + CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM articles a
                            WHERE a.cluster_id = c.cluster_id
                            AND a.title ILIKE s.pattern
                        ) THEN 30 ELSE 0
                    END
                    + CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM articles a
                            WHERE a.cluster_id = c.cluster_id
                            AND a.content ILIKE s.pattern
                        ) THEN 12 ELSE 0
                    END
                    + CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM articles a
                            WHERE a.cluster_id = c.cluster_id
                            AND a.source ILIKE s.pattern
                        ) THEN 10 ELSE 0
                    END
                ) AS match_score
            FROM clusters c
            CROSS JOIN search s
            WHERE c.cluster_id <> 'UNCATEGORIZED'
            AND (
                c.cluster_name ILIKE s.pattern
            OR c.cluster_summary ILIKE s.pattern
            OR EXISTS (
                SELECT 1
                FROM articles a
                WHERE a.cluster_id = c.cluster_id
                AND (
                    a.title ILIKE s.pattern
                    OR a.content ILIKE s.pattern
                    OR a.source ILIKE s.pattern
                )
            )
            OR EXISTS (
                SELECT 1
                FROM cluster_entities ce
                WHERE ce.cluster_id = c.cluster_id
                AND ce.entity_name ILIKE s.pattern
            )
            OR EXISTS (
                SELECT 1
                FROM articles a
                JOIN article_entities ae ON ae.article_id = a.article_id
                WHERE a.cluster_id = c.cluster_id
                AND ae.entity_name ILIKE s.pattern
            )
            )
        ),
        entity_rank AS (
            SELECT
                cluster_id,
                entity_type,
                entity_name,
                frequency,
                ROW_NUMBER() OVER (
                    PARTITION BY cluster_id
                    ORDER BY frequency DESC, entity_name
                ) AS row_number
            FROM cluster_entities
        ),
        entity_payload AS (
            SELECT
                cluster_id,
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'entity_type', entity_type,
                        'entity_name', entity_name,
                        'frequency', frequency
                    )
                    ORDER BY frequency DESC, entity_name
                ) AS entities
            FROM entity_rank
            WHERE row_number <= 6
            GROUP BY cluster_id
        )
        SELECT
            c.cluster_id,
            c.cluster_name,
            c.cluster_summary,
            c.article_count,
            COALESCE(ac.actual_article_count, 0) AS actual_article_count,
            c.updated_at,
            NULL AS top_source,
            NULL AS top_source_count,
            COALESCE(ep.entities, '[]'::json) AS entities,
            mc.matched_fields,
            mc.match_score
        FROM matched_clusters mc
        JOIN clusters c ON c.cluster_id = mc.cluster_id
        LEFT JOIN article_counts ac ON ac.cluster_id = c.cluster_id
        LEFT JOIN entity_payload ep ON ep.cluster_id = c.cluster_id
        WHERE c.cluster_id <> 'UNCATEGORIZED'
        ORDER BY
            mc.match_score DESC,
            COALESCE(ac.actual_article_count, c.article_count, 0) DESC,
            c.updated_at DESC NULLS LAST
        LIMIT %s
        """

        self.cursor.execute(
            query,
            (
                pattern,
                limit
            )
        )

        results = []

        for row in self.cursor.fetchall():

            cluster = self._format_news_cluster_row(row[:9])
            cluster["matched_fields"] = row[9] or []
            cluster["match_score"] = row[10] or 0
            results.append(cluster)

        return results

    def list_common_news_topics(
        self,
        limit=500
    ):
        """Return common searchable news topics from cluster and article entities."""

        limit = max(
            1,
            min(
                int(limit or 500),
                500
            )
        )
        query = """
        WITH topic_source AS (
            SELECT
                entity_name,
                entity_type,
                COALESCE(frequency, 1) AS weight,
                cluster_id::TEXT AS cluster_ref,
                NULL::TEXT AS article_ref
            FROM cluster_entities
            WHERE NULLIF(TRIM(entity_name), '') IS NOT NULL

            UNION ALL

            SELECT
                entity_name,
                entity_type,
                1 AS weight,
                NULL::TEXT AS cluster_ref,
                article_id::TEXT AS article_ref
            FROM article_entities
            WHERE NULLIF(TRIM(entity_name), '') IS NOT NULL
        ),
        normalized_topics AS (
            SELECT
                LOWER(TRIM(entity_name)) AS topic_key,
                TRIM(entity_name) AS topic,
                COALESCE(NULLIF(TRIM(entity_type), ''), 'keyword') AS entity_type,
                weight,
                cluster_ref,
                article_ref
            FROM topic_source
        )
        SELECT
            topic_key,
            MIN(topic) AS topic,
            MIN(entity_type) AS entity_type,
            SUM(weight)::INTEGER AS frequency,
            COUNT(DISTINCT cluster_ref)::INTEGER AS cluster_count,
            COUNT(DISTINCT article_ref)::INTEGER AS article_count
        FROM normalized_topics
        GROUP BY topic_key
        ORDER BY
            SUM(weight) DESC,
            COUNT(DISTINCT cluster_ref) DESC,
            MIN(topic)
        LIMIT %s
        """

        self.cursor.execute(
            query,
            (limit,)
        )

        return [
            self._format_news_topic_row(row)
            for row in self.cursor.fetchall()
        ]

    def _format_news_cluster_row(
        self,
        row
    ):
        """Convert a cluster SQL row into the dashboard/API payload shape."""

        if not row:

            return None

        return {
            "cluster_id": row[0],
            "cluster_name": row[1],
            "cluster_summary": row[2],
            "article_count": row[3] or 0,
            "actual_article_count": row[4] or 0,
            "updated_at": row[5].isoformat() if row[5] else None,
            "top_source": row[6],
            "top_source_count": row[7] or 0,
            "entities": row[8] or []
        }

    def _format_news_source_row(
        self,
        row
    ):
        """Convert a source count row into a JSON-friendly dict."""

        return {
            "source": row[0],
            "article_count": row[1] or 0
        }

    def _format_news_entity_row(
        self,
        row
    ):
        """Convert an entity row into a JSON-friendly dict."""

        return {
            "entity_type": row[0],
            "entity_name": row[1],
            "frequency": row[2] or 0
        }

    def _format_news_topic_row(
        self,
        row
    ):
        """Convert a common topic row into a JSON-friendly dict."""

        return {
            "topic_key": row[0],
            "topic": row[1],
            "entity_type": row[2],
            "frequency": row[3] or 0,
            "cluster_count": row[4] or 0,
            "article_count": row[5] or 0
        }

    def _format_news_article_row(
        self,
        row
    ):
        """Convert an article SQL row into the dashboard/API payload shape."""

        return {
            "article_id": str(row[0]),
            "title": row[1],
            "content": row[2],
            "source": row[3],
            "url": row[4],
            "published_at": row[5].isoformat() if row[5] else None,
            "created_at": row[6].isoformat() if row[6] else None
        }

    def close(self):
        """Close cursor and connection for request-scoped/background services."""

        try:

            self.cursor.close()

        finally:

            self.connection.close()

    def _allowed_search_fields(self):
        """Map public search field names to safe database column names."""

        allowed_fields = {
            "full_name": "full_name",
            "date_of_birth": "date_of_birth",
            "dob": "date_of_birth",
            "aadhar_number": "aadhar_number",
            "aadhaar": "aadhar_number",
            "aadhar": "aadhar_number",
            "pan_number": "pan_number",
            "pan": "pan_number",
            "phone_number": "phone_number",
            "phone": "phone_number",
            "email": "email",
            "username": "username",
            "employee_id": "employee_id",
            "department": "department",
            "state": "state"
        }

        if "voter_id_number" in self.extended_document_columns:

            allowed_fields["voter_id_number"] = "voter_id_number"
            allowed_fields["voter_id"] = "voter_id_number"

        if "driving_license_number" in self.extended_document_columns:

            allowed_fields["driving_license_number"] = "driving_license_number"
            allowed_fields["driving_license"] = "driving_license_number"

        if "passport_number" in self.extended_document_columns:

            allowed_fields["passport_number"] = "passport_number"
            allowed_fields["passport"] = "passport_number"

        return allowed_fields

    def _condition_parameters(self, parameter):
        """Normalize one search condition parameter into a tuple for psycopg2."""

        if isinstance(parameter, (list, tuple)):

            return tuple(parameter)

        return (parameter,)

    def _matched_fields_for_identity(
        self,
        identity,
        criteria
    ):
        """Explain which submitted fields caused a DB row to appear."""

        matches = []

        for item in criteria or []:

            field = str(item.get("field") or "").strip()
            searched_value = str(item.get("value") or "").strip()

            if not field or not searched_value:

                continue

            if field == "username":

                matches.extend(
                    self._username_matches_for_identity(
                        identity,
                        searched_value
                    )
                )
                continue

            allowed_fields = self._allowed_search_fields()
            db_field = allowed_fields.get(field)

            if not db_field or db_field == "username":

                continue

            database_value = identity.get(db_field)

            if self._field_value_matches(field, searched_value, database_value):

                matches.append(
                    {
                        "searched_field": field,
                        "searched_value": searched_value,
                        "matched_column": db_field,
                        "matched_value": database_value
                    }
                )

        return matches

    def _username_matches_for_identity(
        self,
        identity,
        searched_value
    ):
        """Explain username matches against email, employee ID, and full name."""

        normalized_username = searched_value.lstrip("@#").strip()
        spaced_username = re.sub(
            r"[._]+",
            " ",
            normalized_username
        )
        matches = []

        for matched_column, candidate_value, search_text in [
            ("email", identity.get("email"), normalized_username),
            ("employee_id", identity.get("employee_id"), normalized_username),
            ("full_name", identity.get("full_name"), spaced_username)
        ]:

            if self._text_contains(candidate_value, search_text):

                matches.append(
                    {
                        "searched_field": "username",
                        "searched_value": searched_value,
                        "matched_column": matched_column,
                        "matched_value": candidate_value
                    }
                )

        return matches

    def _field_value_matches(
        self,
        field,
        searched_value,
        database_value
    ):
        """Mirror DB search normalization to explain frontend match reasons."""

        if field in {
            "aadhaar",
            "aadhar",
            "aadhar_number",
            "phone",
            "phone_number"
        }:

            return self._digits_only(searched_value) in self._digits_only(database_value)

        if field in {
            "pan",
            "pan_number",
            "voter_id",
            "voter_id_number",
            "driving_license",
            "driving_license_number",
            "passport",
            "passport_number"
        }:

            return self._normalize_identifier(searched_value) in self._normalize_identifier(database_value)

        return self._text_contains(database_value, searched_value)

    def _text_contains(
        self,
        database_value,
        searched_value
    ):
        """Case-insensitive contains check used for match explanations."""

        database_text = str(database_value or "").strip().lower()
        searched_text = str(searched_value or "").strip().lower()

        return bool(searched_text and searched_text in database_text)

    def _digits_only(
        self,
        value
    ):
        """Return only digits for phone and Aadhaar match explanations."""

        return re.sub(
            r"\D",
            "",
            str(value or "")
        )

    def _normalize_identifier(
        self,
        value
    ):
        """Return uppercase alphanumeric text for ID match explanations."""

        return re.sub(
            r"[^A-Za-z0-9]",
            "",
            str(value or "")
        ).upper()

    def _build_search_condition(
        self,
        field,
        value
    ):
        """Build a parameterized WHERE clause for one allowed search field."""

        allowed_fields = self._allowed_search_fields()
        field = str(field or "").strip()

        if field not in allowed_fields:

            return None

        db_column = allowed_fields[field]
        search_value = str(value or "").strip()

        if field == "username":

            normalized_username = search_value.lstrip("@#").strip()
            spaced_username = re.sub(
                r"[._]+",
                " ",
                normalized_username
            )

            if not normalized_username:

                return None

            where_clause = """
            (
                CAST(email AS TEXT) ILIKE %s
                OR CAST(employee_id AS TEXT) ILIKE %s
                OR CAST(full_name AS TEXT) ILIKE %s
            )
            """

            return where_clause, (
                f"%{normalized_username}%",
                f"%{normalized_username}%",
                f"%{spaced_username}%"
            )

        if field in {
            "aadhaar",
            "aadhar",
            "aadhar_number",
            "phone",
            "phone_number"
        }:

            where_clause = f"REGEXP_REPLACE(CAST({db_column} AS TEXT), '\\D', '', 'g') ILIKE %s"
            search_value = re.sub(r"\D", "", search_value)

        elif field in {
            "pan",
            "pan_number",
            "voter_id",
            "voter_id_number",
            "driving_license",
            "driving_license_number",
            "passport",
            "passport_number"
        }:

            where_clause = f"UPPER(REGEXP_REPLACE(CAST({db_column} AS TEXT), '[^A-Za-z0-9]', '', 'g')) ILIKE %s"
            search_value = re.sub(r"[^A-Za-z0-9]", "", search_value).upper()

        else:

            where_clause = f"CAST({db_column} AS TEXT) ILIKE %s"

        if not search_value:

            return None

        return where_clause, f"%{search_value}%"

    # -----------------------------------
    # DOCUMENT VERIFICATION
    # -----------------------------------

    def verify_identity_document(
        self,
        extracted_data
    ):
        """Find a database identity that matches the uploaded document number."""

        document_type = self._normalize_document_type(
            extracted_data.get("document_type")
        )
        search_value = None
        search_field = None

        if document_type == "aadhaar":

            search_field = "aadhaar"
            search_value = extracted_data.get("aadhar_number")

        elif document_type == "pan":

            search_field = "pan"
            search_value = extracted_data.get("pan_number")

        elif document_type == "voter_id":

            search_field = "voter_id"
            search_value = extracted_data.get("voter_id_number")

        elif document_type == "driving_license":

            search_field = "driving_license"
            search_value = extracted_data.get("driving_license_number")

        elif document_type == "passport":

            search_field = "passport"
            search_value = extracted_data.get("passport_number")

        if not search_field or not search_value:

            return None

        matches = self.search_identity(
            search_field,
            search_value
        )

        if matches:

            matches[0]["_document_match_type"] = "exact"
            matches[0]["_document_match_field"] = search_field

            return matches[0]

        fuzzy_match = self._find_fuzzy_aadhaar_match(
            search_field,
            search_value
        )

        if fuzzy_match:

            return fuzzy_match

        return None

    def _find_fuzzy_aadhaar_match(
        self,
        search_field,
        search_value

    ):
        """Recover Aadhaar matches when OCR has up to two digit mistakes."""

        if search_field != "aadhaar":

            return None

        search_digits = re.sub(
            r"\D",
            "",
            str(search_value or "")
        )

        if len(search_digits) != 12:

            return None

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE aadhar_number IS NOT NULL
        AND TRIM(CAST(aadhar_number AS TEXT)) <> ''
        LIMIT 5000
        """

        self.cursor.execute(query)

        best_match = None
        best_distance = None

        for row in self.cursor.fetchall():

            database_digits = re.sub(
                r"\D",
                "",
                str(row[3] or "")
            )

            if len(database_digits) != 12:

                continue

            distance = self._hamming_distance(
                search_digits,
                database_digits
            )

            if distance <= 2 and (best_distance is None or distance < best_distance):

                best_distance = distance
                best_match = self._format_identity_row(row)

        if not best_match:

            return None

        best_match["_document_match_type"] = "fuzzy_ocr_correction"
        best_match["_document_match_field"] = search_field
        best_match["_document_match_distance"] = best_distance

        return best_match

    def _hamming_distance(
        self,
        value_one,
        value_two
    ):
        """Count character positions that differ between equal-length strings."""

        if len(value_one) != len(value_two):

            return max(
                len(value_one),
                len(value_two)
            )

        return sum(
            character_one != character_two
            for character_one, character_two in zip(value_one, value_two)
        )

    def _format_identity_row(
        self,
        row
    ):
        """Convert a `demodataset` row into the identity JSON contract."""

        return {

            "employee_id": row[0],

            "full_name": row[1],

            "date_of_birth": str(row[2]),

            "aadhar_number": row[3],

            "pan_number": row[4],

            "voter_id_number": row[5],

            "driving_license_number": row[6],

            "passport_number": row[7],

            "phone_number": row[8],

            "email": row[9],

            "department": row[10],

            "state": row[11],

            "photo_path": row[12]
        }

    def _normalize_document_type(
        self,
        document_type
    ):
        """Normalize document labels before selecting DB search fields."""

        normalized_type = re.sub(
            r"[^a-z0-9]+",
            "_",
            str(document_type or "").lower().strip()
        ).strip("_")

        aliases = {
            "aadhar": "aadhaar",
            "aadhar_card": "aadhaar",
            "aadhaar_card": "aadhaar",
            "pan_card": "pan",
            "voter": "voter_id",
            "voter_card": "voter_id",
            "voter_id_card": "voter_id",
            "driving_licence": "driving_license",
            "license": "driving_license",
            "licence": "driving_license"
        }

        return aliases.get(normalized_type, normalized_type)

    # -----------------------------------
    # FACE SEARCH DATASET
    # -----------------------------------

    def get_identities_with_photos(self):
        """Return all identities that can participate in face search."""

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE photo_path IS NOT NULL
        AND TRIM(CAST(photo_path AS TEXT)) <> ''
        """

        self.cursor.execute(query)

        results = self.cursor.fetchall()

        formatted_results = []

        for row in results:

            formatted_results.append({

                "employee_id": row[0],

                "full_name": row[1],

                "date_of_birth": str(row[2]),

                "aadhar_number": row[3],

                "pan_number": row[4],

                "voter_id_number": row[5],

                "driving_license_number": row[6],

                "passport_number": row[7],

                "phone_number": row[8],

                "email": row[9],

                "department": row[10],

                "state": row[11],

                "photo_path": row[12]
            })

        return formatted_results

    def _select_extended_column(self, column_name):
        """Select optional columns safely even when older DBs do not have them."""

        if column_name in self.extended_document_columns:

            return column_name

        return f"NULL AS {column_name}"

    # -----------------------------------
    # REGISTRATION
    # -----------------------------------

    def register_identity(
        self,
        identity_data
    ):
        """Create a new identity record after required-field and duplicate checks."""

        employee_id = str(identity_data.get("employee_id") or "").strip()

        if not employee_id:

            raise ValueError("Employee ID is required")

        if not str(identity_data.get("full_name") or "").strip():

            raise ValueError("Full name is required")

        self.cursor.execute(
            """
            SELECT employee_id
            FROM demodataset
            WHERE employee_id = %s
            LIMIT 1
            """,
            (employee_id,)
        )

        if self.cursor.fetchone():

            raise ValueError(f"Employee ID already exists: {employee_id}")

        query = """
        INSERT INTO demodataset (
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            voter_id_number,
            driving_license_number,
            passport_number,
            phone_number,
            email,
            department,
            state,
            photo_path
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        self.cursor.execute(
            query,
            (
                employee_id,
                identity_data.get("full_name"),
                identity_data.get("date_of_birth") or None,
                identity_data.get("aadhar_number") or None,
                identity_data.get("pan_number") or None,
                identity_data.get("voter_id_number") or None,
                identity_data.get("driving_license_number") or None,
                identity_data.get("passport_number") or None,
                identity_data.get("phone_number") or None,
                identity_data.get("email") or None,
                identity_data.get("department") or None,
                identity_data.get("state") or None,
                identity_data.get("photo_path") or None
            )
        )
        self.connection.commit()

        matches = self.search_identity(
            "employee_id",
            employee_id
        )

        if matches:

            return matches[0]

        return identity_data

    # -----------------------------------
    # ADMIN CRUD
    # -----------------------------------

    def list_identities(
        self,
        limit=100
    ):
        """Return a limited admin view of identity records ordered by employee ID."""

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        ORDER BY employee_id
        LIMIT %s
        """

        self.cursor.execute(
            query,
            (limit,)
        )

        return [
            self._format_identity_row(row)
            for row in self.cursor.fetchall()
        ]

    def get_identity_by_employee_id(
        self,
        employee_id
    ):
        """Fetch one identity record for update/delete/admin display."""

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE employee_id = %s
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (employee_id,)
        )

        row = self.cursor.fetchone()

        if not row:

            return None

        return self._format_identity_row(row)

    def create_identity_admin(
        self,
        identity_data
    ):
        """Admin create wrapper that normalizes payload before registration."""

        return self.register_identity(
            self._normalize_identity_payload(identity_data)
        )

    def update_identity_admin(
        self,
        employee_id,
        identity_data
    ):
        """Update an existing identity while preserving photo when not replaced."""

        employee_id = str(employee_id or "").strip()

        if not employee_id:

            raise ValueError("Employee ID is required")

        existing_identity = self.get_identity_by_employee_id(employee_id)

        if not existing_identity:

            raise ValueError(f"Identity not found: {employee_id}")

        normalized_data = self._normalize_identity_payload(identity_data)
        full_name = normalized_data.get("full_name")

        if not full_name:

            raise ValueError("Full name is required")

        photo_path = normalized_data.get("photo_path") or existing_identity.get("photo_path")

        query = """
        UPDATE demodataset
        SET
            full_name = %s,
            date_of_birth = %s,
            aadhar_number = %s,
            pan_number = %s,
            voter_id_number = %s,
            driving_license_number = %s,
            passport_number = %s,
            phone_number = %s,
            email = %s,
            department = %s,
            state = %s,
            photo_path = %s
        WHERE employee_id = %s
        """

        self.cursor.execute(
            query,
            (
                full_name,
                normalized_data.get("date_of_birth"),
                normalized_data.get("aadhar_number"),
                normalized_data.get("pan_number"),
                normalized_data.get("voter_id_number"),
                normalized_data.get("driving_license_number"),
                normalized_data.get("passport_number"),
                normalized_data.get("phone_number"),
                normalized_data.get("email"),
                normalized_data.get("department"),
                normalized_data.get("state"),
                photo_path,
                employee_id
            )
        )
        self.connection.commit()

        return self.get_identity_by_employee_id(employee_id)

    def delete_identity_admin(
        self,
        employee_id
    ):
        """Delete an identity and return the removed record for confirmation."""

        employee_id = str(employee_id or "").strip()

        if not employee_id:

            raise ValueError("Employee ID is required")

        existing_identity = self.get_identity_by_employee_id(employee_id)

        if not existing_identity:

            raise ValueError(f"Identity not found: {employee_id}")

        self.cursor.execute(
            """
            DELETE FROM demodataset
            WHERE employee_id = %s
            """,
            (employee_id,)
        )
        self.connection.commit()

        return existing_identity

    def _normalize_identity_payload(
        self,
        identity_data
    ):
        """Strip strings and convert empty form values into database NULLs."""

        identity_data = identity_data or {}
        normalized_data = {}

        for field_name in {
            "employee_id",
            "full_name",
            "date_of_birth",
            "aadhar_number",
            "pan_number",
            "voter_id_number",
            "driving_license_number",
            "passport_number",
            "phone_number",
            "email",
            "department",
            "state",
            "photo_path"
        }:

            value = identity_data.get(field_name)

            if value is None:

                normalized_data[field_name] = None

            else:

                normalized_data[field_name] = str(value).strip() or None

        return normalized_data

    # -----------------------------------
    # MANUAL REVIEW QUEUE
    # -----------------------------------

    def create_manual_review_case(
        self,
        extracted_data,
        database_match,
        face_result,
        decision,
        uploaded_document_path
    ):
        """Store a document verification case that needs human review."""

        query = """
        INSERT INTO manual_review_cases (
            status,
            document_type,
            employee_id,
            full_name,
            uploaded_document_path,
            extracted_data,
            database_match,
            face_result,
            decision
        )
        VALUES (
            'PENDING', %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """

        self.cursor.execute(
            query,
            (
                extracted_data.get("document_type"),
                (database_match or {}).get("employee_id"),
                (database_match or {}).get("full_name") or extracted_data.get("full_name"),
                uploaded_document_path,
                json.dumps(extracted_data, default=str),
                json.dumps(database_match, default=str),
                json.dumps(face_result, default=str),
                json.dumps(decision, default=str)
            )
        )
        case_id = self.cursor.fetchone()[0]
        self.connection.commit()

        return self.get_manual_review_case(case_id)

    def get_manual_review_case(
        self,
        case_id
    ):
        """Fetch a single manual review case by numeric ID."""

        self.cursor.execute(
            """
            SELECT
                id,
                status,
                document_type,
                employee_id,
                full_name,
                uploaded_document_path,
                extracted_data,
                database_match,
                face_result,
                decision,
                reviewer_notes,
                created_at,
                updated_at
            FROM manual_review_cases
            WHERE id = %s
            """,
            (case_id,)
        )

        row = self.cursor.fetchone()

        if not row:

            return None

        return self._format_manual_review_case(row)

    def list_manual_review_cases(
        self,
        status="PENDING"
    ):
        """List review cases by status for the dashboard queue."""

        allowed_statuses = {
            "PENDING",
            "APPROVED",
            "REJECTED",
            "ALL"
        }

        normalized_status = str(status or "PENDING").upper()

        if normalized_status not in allowed_statuses:

            normalized_status = "PENDING"

        if normalized_status == "ALL":

            query = """
            SELECT
                id,
                status,
                document_type,
                employee_id,
                full_name,
                uploaded_document_path,
                extracted_data,
                database_match,
                face_result,
                decision,
                reviewer_notes,
                created_at,
                updated_at
            FROM manual_review_cases
            ORDER BY created_at DESC
            LIMIT 100
            """
            params = ()

        else:

            query = """
            SELECT
                id,
                status,
                document_type,
                employee_id,
                full_name,
                uploaded_document_path,
                extracted_data,
                database_match,
                face_result,
                decision,
                reviewer_notes,
                created_at,
                updated_at
            FROM manual_review_cases
            WHERE status = %s
            ORDER BY created_at DESC
            LIMIT 100
            """
            params = (normalized_status,)

        self.cursor.execute(query, params)

        return [
            self._format_manual_review_case(row)
            for row in self.cursor.fetchall()
        ]

    def update_manual_review_case(
        self,
        case_id,
        reviewer_decision,
        reviewer_notes=""
    ):
        """Apply reviewer decision and notes to a manual review case."""

        normalized_decision = str(reviewer_decision or "").upper()

        if normalized_decision not in {
            "APPROVED",
            "REJECTED",
            "PENDING"
        }:

            raise ValueError("Reviewer decision must be APPROVED, REJECTED, or PENDING")

        self.cursor.execute(
            """
            UPDATE manual_review_cases
            SET
                status = %s,
                reviewer_notes = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
            """,
            (
                normalized_decision,
                reviewer_notes,
                case_id
            )
        )

        updated = self.cursor.fetchone()

        if not updated:

            self.connection.rollback()
            raise ValueError(f"Manual review case not found: {case_id}")

        self.connection.commit()

        return self.get_manual_review_case(case_id)

    def _format_manual_review_case(
        self,
        row
    ):
        """Convert a manual review SQL row into API/dashboard format."""

        return {
            "id": row[0],
            "status": row[1],
            "document_type": row[2],
            "employee_id": row[3],
            "full_name": row[4],
            "uploaded_document_path": row[5],
            "extracted_data": self._load_json(row[6]),
            "database_match": self._load_json(row[7]),
            "face_result": self._load_json(row[8]),
            "decision": self._load_json(row[9]),
            "reviewer_notes": row[10],
            "created_at": str(row[11]),
            "updated_at": str(row[12])
        }

    def _load_json(
        self,
        value
    ):
        """Decode stored JSON text while tolerating legacy plain strings."""

        if not value:

            return None

        try:

            return json.loads(value)

        except (TypeError, json.JSONDecodeError):

            return value

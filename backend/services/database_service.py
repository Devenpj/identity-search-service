"""PostgreSQL data access layer for identity, OSINT, and review workflows."""

import psycopg2
from psycopg2 import errors
import json
import re

from utils.logger import get_logger


logger = get_logger("identity-search-service.database")


class DatabaseService:
    """Own all direct SQL used by the FastAPI backend."""

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
        self._ensure_document_columns()
        self._ensure_manual_review_table()
        self._ensure_osint_jobs_table()
        self.extended_document_columns = self._get_existing_extended_columns()

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
        """Search `demodataset` using multiple OR-connected criteria."""

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
        WHERE {" OR ".join(conditions)}
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

        logger.info(
            "OSINT DB state: job_id=%s status=PENDING targets=%s",
            formatted_job.get("job_id") if formatted_job else job_id,
            len(targets or [])
        )

        return formatted_job

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

    # -----------------------------------
    # NEWS INTELLIGENCE
    # -----------------------------------

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
            WHERE c.cluster_name ILIKE s.pattern
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

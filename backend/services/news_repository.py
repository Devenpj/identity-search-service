import json

try:
    from utils.logger import get_logger
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from utils.logger import get_logger


logger = get_logger("identity-search-service.database")


class NewsRepositoryMixin:
    """Repository methods split out of DatabaseService."""

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
        """Return the latest news clusters with article/source/entity context."""

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
            c.updated_at DESC NULLS LAST,
            COALESCE(ac.actual_article_count, c.article_count, 0) DESC,
            c.cluster_id DESC
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


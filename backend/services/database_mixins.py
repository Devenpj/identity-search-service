"""Reusable database mixins for shared persistence behavior."""

try:
    from utils.logger import get_logger
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from utils.logger import get_logger


logger = get_logger("identity-search-service.database")


class AsyncJobLifecycleMixin:
    """Encapsulate common async-job state transitions for repository classes."""

    _JOB_TABLES = {
        "face_search_jobs",
        "video_face_jobs",
        "document_validation_jobs",
        "osint_jobs"
    }

    def _job_table(self, table_name):
        """Return a whitelisted job table name for dynamic internal SQL."""

        if table_name not in self._JOB_TABLES:

            raise ValueError(f"Unsupported job table: {table_name}")

        return table_name

    def _coerce_minutes(self, value, default_minutes):
        """Normalize timeout minutes while keeping sane lower bounds."""

        try:

            return max(1, int(value or default_minutes))

        except (TypeError, ValueError):

            return int(default_minutes)

    def _mark_async_job_failed(
        self,
        table_name,
        job_id,
        error_message,
        default_error,
        label,
        progress_message=None
    ):
        """Persist a FAILED status for any async job table."""

        table_name = self._job_table(table_name)
        normalized_error = str(error_message or default_error)

        if progress_message:

            query = f"""
            UPDATE {table_name}
            SET
                status = 'FAILED',
                progress_percent = 100,
                progress_message = %s,
                error_message = %s,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            """
            params = (
                progress_message,
                normalized_error,
                job_id
            )

        else:

            query = f"""
            UPDATE {table_name}
            SET
                status = 'FAILED',
                error_message = %s,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            """
            params = (
                normalized_error,
                job_id
            )

        self.cursor.execute(query, params)
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:

            logger.error(
                "%s DB state: job_id=%s status=FAILED error=%s",
                label,
                job_id,
                normalized_error
            )

        else:

            logger.error(
                "%s DB state update failed: job_id=%s status=FAILED reason=job_not_found error=%s",
                label,
                job_id,
                normalized_error
            )

        return updated_rows

    def _mark_stale_async_jobs_failed(
        self,
        table_name,
        max_age_minutes,
        default_minutes,
        error_message,
        label,
        progress_message=None,
        timestamp_expression="COALESCE(started_at, created_at)"
    ):
        """Mark old PENDING/PROCESSING jobs failed and return expired IDs."""

        table_name = self._job_table(table_name)
        stale_minutes = self._coerce_minutes(max_age_minutes, default_minutes)

        if progress_message:

            query = f"""
            UPDATE {table_name}
            SET
                status = 'FAILED',
                progress_percent = 100,
                progress_message = %s,
                error_message = %s,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('PENDING', 'PROCESSING')
            AND {timestamp_expression} < (
                CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
            )
            RETURNING job_id
            """
            params = (
                progress_message,
                error_message,
                stale_minutes
            )

        else:

            query = f"""
            UPDATE {table_name}
            SET
                status = 'FAILED',
                error_message = %s,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('PENDING', 'PROCESSING')
            AND {timestamp_expression} < (
                CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
            )
            RETURNING job_id
            """
            params = (
                error_message,
                stale_minutes
            )

        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        self.connection.commit()
        expired_job_ids = [
            row[0]
            for row in rows
        ]

        if expired_job_ids:

            logger.error(
                "%s stale jobs marked failed: count=%s max_age_minutes=%s job_ids=%s",
                label,
                len(expired_job_ids),
                stale_minutes,
                expired_job_ids
            )

        return expired_job_ids

    def _update_job_progress(
        self,
        table_name,
        job_id,
        progress_percent,
        progress_message
    ):
        """Update shared progress fields on an async job table."""

        table_name = self._job_table(table_name)
        query = f"""
        UPDATE {table_name}
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

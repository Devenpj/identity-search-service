"""Client for submitting identity-search targets to the OSINT engine."""

from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import requests

from config import settings
from utils.logger import get_logger


logger = get_logger("identity-search-service.osint")


class OSINTService:
    """Send OSINT jobs, validate provider response, and build callback URLs."""

    def is_configured(self):
        """Return True only when all required OSINT environment values exist."""

        return bool(
            settings.OSINT_API_BASE_URL
            and settings.OSINT_API_KEY
            and settings.OSINT_CALLBACK_URL
        )

    def configuration_message(self):
        """Describe missing OSINT settings for logs and failed job records."""

        missing_values = []

        if not settings.OSINT_API_BASE_URL:
            missing_values.append("OSINT_API_BASE_URL")

        if not settings.OSINT_API_KEY:
            missing_values.append("OSINT_API_KEY")

        if not settings.OSINT_CALLBACK_URL:
            missing_values.append("OSINT_CALLBACK_URL")

        if not missing_values:
            return None

        return "Missing OSINT configuration: " + ", ".join(missing_values)

    def submit_scan(
        self,
        job_id,
        targets,
        database_service
    ):
        """Submit a queued OSINT job and move it to PROCESSING or FAILED.

        The project owns one stable job ID like JOB00001. The OSINT provider
        must echo that same ID in the immediate response and final webhook.
        """

        if not self.is_configured():

            database_service.mark_osint_job_failed(
                job_id,
                self.configuration_message()
            )

            return

        request_payload = {
            "job_id": job_id,
            "targets": targets,
            "callback_url": self._callback_url()
        }
        scan_url = urljoin(
            f"{settings.OSINT_API_BASE_URL}/",
            settings.OSINT_SCAN_PATH.lstrip("/")
        )

        try:

            logger.info(
                "Submitting OSINT job: job_id=%s total_targets=%s",
                job_id,
                len(targets)
            )

            response = requests.post(
                scan_url,
                headers={
                    "X-API-Key": settings.OSINT_API_KEY,
                    "Content-Type": "application/json"
                },
                json=request_payload,
                timeout=settings.OSINT_REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            provider_response = response.json()
            response_job_id = str(
                provider_response.get("job_id")
                or ""
            ).strip()

            if not response_job_id:

                raise ValueError("OSINT provider response did not include job_id")

            if response_job_id != job_id:

                raise ValueError(
                    f"OSINT provider returned mismatched job_id: {response_job_id}"
                )

            database_service.mark_osint_job_submitted(
                job_id=job_id,
                provider_response=provider_response
            )

            logger.info(
                "OSINT job submitted: job_id=%s",
                job_id
            )

        except Exception as error:

            logger.exception(
                "OSINT job submission failed: job_id=%s",
                job_id
            )
            database_service.mark_osint_job_failed(
                job_id,
                str(error)
            )

    def _callback_url(self):
        """Attach the webhook token to the configured callback URL."""

        callback_url = settings.OSINT_CALLBACK_URL

        split_url = urlsplit(callback_url)
        query_values = dict(
            parse_qsl(
                split_url.query,
                keep_blank_values=True
            )
        )

        if settings.OSINT_WEBHOOK_TOKEN:

            query_values["webhook_token"] = settings.OSINT_WEBHOOK_TOKEN

        return urlunsplit(
            (
                split_url.scheme,
                split_url.netloc,
                split_url.path,
                urlencode(query_values),
                split_url.fragment
            )
        )

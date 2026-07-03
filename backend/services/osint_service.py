"""Client for submitting identity-search targets to the OSINT engine."""

from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import requests
import socket
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings
from utils.logger import get_logger


logger = get_logger("identity-search-service.osint")


class OSINTService:
    """Send OSINT jobs, validate provider response, and build callback URLs."""

    def __init__(self):
        """Create one retry-enabled HTTP session for OSINT engine calls."""

        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            connect=5,
            read=2,
            backoff_factor=1,
            status_forcelist=[
                429,
                500,
                502,
                503,
                504
            ],
            allowed_methods=frozenset(
                [
                    "POST"
                ]
            ),
            raise_on_status=False
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy
        )
        self.session.mount(
            "http://",
            adapter
        )
        self.session.mount(
            "https://",
            adapter
        )

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
            logger.error(
                "OSINT job blocked before submit: job_id=%s error=%s",
                job_id,
                self.configuration_message()
            )

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
                "OSINT submit started: job_id=%s total_targets=%s scan_url=%s callback_url=%s",
                job_id,
                len(targets),
                scan_url,
                request_payload["callback_url"]
            )
            logger.info(
                "OSINT submit payload: job_id=%s targets=%s",
                job_id,
                self._target_summary(targets)
            )

            self._verify_engine_reachable(
                job_id,
                scan_url
            )

            logger.info(
                "OSINT submit retry policy: job_id=%s total_retries=5 timeout_seconds=%s",
                job_id,
                settings.OSINT_REQUEST_TIMEOUT_SECONDS
            )

            response = self.session.post(
                scan_url,
                headers={
                    "X-API-Key": settings.OSINT_API_KEY,
                    "Content-Type": "application/json"
                },
                json=request_payload,
                timeout=settings.OSINT_REQUEST_TIMEOUT_SECONDS
            )
            logger.info(
                "OSINT engine immediate response received: job_id=%s http_status=%s",
                job_id,
                response.status_code
            )
            try:

                response.raise_for_status()

            except requests.exceptions.HTTPError as error:

                raise RuntimeError(
                    self._explain_http_error(
                        error,
                        response
                    )
                ) from error

            try:

                provider_response = response.json()

            except ValueError as error:

                raise RuntimeError(
                    "OSINT engine returned a non-JSON response. "
                    "Machine: OSINT_ENGINE. "
                    f"URL: {scan_url}. "
                    "Reason: provider endpoint responded, but body was not valid JSON."
                ) from error

            logger.info(
                "OSINT engine immediate response body: job_id=%s response=%s",
                job_id,
                provider_response
            )
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
                "OSINT submit completed: job_id=%s db_status=PROCESSING",
                job_id
            )

        except requests.exceptions.RequestException as error:

            error_message = self._explain_request_error(
                error,
                scan_url
            )

            logger.exception(
                "OSINT submit failed: job_id=%s %s",
                job_id,
                error_message
            )
            database_service.mark_osint_job_failed(
                job_id,
                error_message
            )

        except Exception as error:

            logger.exception(
                "OSINT submit failed: job_id=%s error=%s",
                job_id,
                str(error)
            )
            database_service.mark_osint_job_failed(
                job_id,
                str(error)
            )

    def _verify_engine_reachable(
        self,
        job_id,
        scan_url
    ):
        """Fail fast when the OSINT engine host/port cannot be reached."""

        split_url = urlsplit(scan_url)
        host = split_url.hostname
        port = split_url.port or (
            443 if split_url.scheme == "https" else 80
        )
        timeout_seconds = min(
            float(settings.OSINT_REQUEST_TIMEOUT_SECONDS or 10),
            3.0
        )

        logger.info(
            "OSINT network preflight started: job_id=%s machine=OSINT_ENGINE host=%s port=%s timeout_seconds=%s",
            job_id,
            host,
            port,
            timeout_seconds
        )

        try:

            with socket.create_connection(
                (
                    host,
                    port
                ),
                timeout=timeout_seconds
            ):

                logger.info(
                    "OSINT network preflight passed: job_id=%s machine=OSINT_ENGINE host=%s port=%s",
                    job_id,
                    host,
                    port
                )

        except OSError as error:

            error_message = (
                "OSINT connection failure before submit. "
                "Machine: OSINT_ENGINE. "
                f"Host: {host}. Port: {port}. "
                f"Reason: {error}. "
                "Likely causes: OSINT backend is not running on that machine, "
                "Windows Firewall is blocking inbound port 8000 on the OSINT machine, "
                "the IP address is wrong, or both computers are not on the same network/VPN."
            )

            logger.error(
                "OSINT network preflight failed: job_id=%s %s",
                job_id,
                error_message
            )

            raise ConnectionError(error_message) from error

    def _explain_http_error(
        self,
        error,
        response
    ):
        """Return a terminal-friendly reason for HTTP failures from OSINT engine."""

        status_code = getattr(
            response,
            "status_code",
            "-"
        )
        response_text = getattr(
            response,
            "text",
            ""
        )

        return (
            "OSINT engine rejected the request. "
            "Machine: OSINT_ENGINE. "
            f"HTTP status: {status_code}. "
            f"Reason: {error}. "
            f"Response body: {response_text[:500]}"
        )

    def _explain_request_error(
        self,
        error,
        scan_url
    ):
        """Return a clear machine/reason diagnosis for requests failures."""

        split_url = urlsplit(scan_url)
        host = split_url.hostname
        port = split_url.port or (
            443 if split_url.scheme == "https" else 80
        )

        if isinstance(
            error,
            requests.exceptions.ConnectTimeout
        ):

            reason = (
                "OSINT engine did not accept the connection before timeout. "
                "Likely cause: server down, firewall block, wrong IP, or network/VPN issue."
            )

        elif isinstance(
            error,
            requests.exceptions.ReadTimeout
        ):

            reason = (
                "OSINT engine accepted the connection but did not reply in time. "
                "Likely cause: OSINT endpoint is overloaded, stuck, or timeout is too low."
            )

        elif isinstance(
            error,
            requests.exceptions.ConnectionError
        ):

            reason = (
                "Backend could not open a TCP connection to OSINT engine. "
                "Likely cause: OSINT server not running, firewall block, wrong IP, "
                "port mismatch, or different network/VPN."
            )

        else:

            reason = "Requests library failed while calling the OSINT engine."

        return (
            "OSINT submit request failed. "
            "Machine: OSINT_ENGINE. "
            f"Host: {host}. Port: {port}. "
            f"URL: {scan_url}. "
            f"Reason: {reason} "
            f"Raw error: {error}"
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

    def _target_summary(self, targets):
        """Return readable target keys and masked values for terminal logs."""

        summary = []

        for target in targets or []:
            key = str(target.get("key") or "-")
            raw_value = target.get("value")

            if isinstance(raw_value, dict):
                filename = str(raw_value.get("filename") or "face_image")
                size_bytes = int(raw_value.get("size_bytes") or 0)
                encoding = str(raw_value.get("encoding") or "binary")
                masked_value = f"{filename} ({size_bytes} bytes, {encoding})"
            else:
                value = str(raw_value or "")
                masked_value = value

                if "@" in value and "." in value:
                    name, _, domain = value.partition("@")
                    masked_value = f"{name[:2]}***@{domain}"
                elif len(value) > 6:
                    masked_value = f"{value[:3]}***{value[-2:]}"

            summary.append(
                {
                    "key": key,
                    "value": masked_value
                }
            )

        return summary

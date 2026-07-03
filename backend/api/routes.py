"""FastAPI routes for identity search, verification, admin, and OSINT APIs.

The Streamlit dashboard calls these routes. Each route validates request input,
delegates the real work to a service class, and returns JSON shaped for the UI.
Longer operations such as OSINT submission are pushed into FastAPI background
tasks while the final OSINT payload returns through the webhook endpoint.
"""

import base64
import hmac
import io
import json
import os
import re
from datetime import datetime
from uuid import uuid4

import requests
from PIL import Image
from PIL import UnidentifiedImageError
from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi import Form
from fastapi import Header
from fastapi import UploadFile
from fastapi import File
from fastapi import Query
from fastapi import Body
from fastapi.responses import JSONResponse

try:
    from ..config import settings
    from ..services.database_service import DatabaseService
    from ..services.decision_service import DecisionService
    from ..services.document_verification_service import DocumentVerificationService
    from ..services.file_service import FileService
    from ..services.face_service import FaceVerificationService
    from ..services.ocr_service import OCRService
    from ..services.osint_normalizer_service import OSINTNormalizerService
    from ..services.osint_service import OSINTService
    from ..services.news_database_service import NewsDatabaseService
    from ..services.risk_service import RiskScoringService
except ImportError:
    from config import settings
    from services.database_service import DatabaseService
    from services.decision_service import DecisionService
    from services.document_verification_service import DocumentVerificationService
    from services.file_service import FileService
    from services.face_service import FaceVerificationService
    from services.ocr_service import OCRService
    from services.osint_normalizer_service import OSINTNormalizerService
    from services.osint_service import OSINTService
    from services.news_database_service import NewsDatabaseService
    from services.risk_service import RiskScoringService

from utils.logger import configure_logging
from utils.logger import get_logger

configure_logging()
logger = get_logger("identity-search-service.backend")

app = FastAPI()

database_service = DatabaseService()
decision_service = DecisionService()
file_service = FileService()
face_service = FaceVerificationService()
ocr_service = OCRService()
osint_normalizer_service = OSINTNormalizerService()
osint_service = OSINTService()
risk_service = RiskScoringService()
document_verification_service = DocumentVerificationService(
    file_service,
    ocr_service,
    database_service,
    face_service,
    risk_service,
    decision_service
)


def database_health_payload():
    """Check PostgreSQL connectivity without exposing credentials."""

    health_database_service = None

    try:
        health_database_service = DatabaseService()
        health_database_service.cursor.execute("SELECT 1")
        health_database_service.cursor.fetchone()

        return {
            "status": "ok",
            "database": "excel_import",
            "message": "PostgreSQL connection is healthy"
        }, 200

    except Exception as error:
        logger.exception("Database health check failed")

        return {
            "status": "error",
            "database": "excel_import",
            "message": str(error)
        }, 503

    finally:
        if health_database_service:
            health_database_service.close()


def osint_health_payload(check_network=False):
    """Check OSINT configuration and optionally verify network reachability."""

    configured = osint_service.is_configured()
    payload = {
        "status": "ok" if configured else "error",
        "configured": configured,
        "api_base_url": settings.OSINT_API_BASE_URL or None,
        "scan_path": settings.OSINT_SCAN_PATH,
        "callback_configured": bool(settings.OSINT_CALLBACK_URL),
        "message": "OSINT configuration is present"
        if configured
        else osint_service.configuration_message()
    }
    status_code = 200 if configured else 503

    if not configured or not check_network:
        return payload, status_code

    try:
        response = requests.get(
            settings.OSINT_API_BASE_URL,
            timeout=3
        )
        payload["network"] = {
            "reachable": True,
            "http_status": response.status_code
        }

    except Exception as error:
        logger.exception("OSINT network health check failed")
        payload["status"] = "error"
        payload["network"] = {
            "reachable": False,
            "error": str(error)
        }
        status_code = 503

    return payload, status_code


def news_database_health_payload():
    """Check the optional external Docker/PostgreSQL news database."""

    if not NewsDatabaseService.is_configured():

        return {
            "status": "ok",
            "configured": False,
            "mode": "local",
            "message": "NEWS_DATABASE_URL is not configured; using local news tables"
        }, 200

    health_news_database_service = None

    try:
        health_news_database_service = NewsDatabaseService()
        health_news_database_service.cursor.execute("SELECT 1")
        health_news_database_service.cursor.fetchone()

        return {
            "status": "ok",
            "configured": True,
            "mode": "external",
            "webhook_configured": bool(settings.NEWS_WEBHOOK_TOKEN),
            "message": "External news database connection is healthy"
        }, 200

    except Exception as error:
        logger.exception("External news database health check failed")

        return {
            "status": "error",
            "configured": True,
            "mode": "external",
            "message": str(error)
        }, 503

    finally:
        if health_news_database_service:
            health_news_database_service.close()


def open_news_database_service():
    """Open the external news DB when configured, otherwise use local tables."""

    if not NewsDatabaseService.is_configured():

        return database_service, False, "local"

    try:
        return NewsDatabaseService(), True, "external"

    except Exception:
        logger.exception(
            "External news database unavailable; using local news tables"
        )

        return database_service, False, "local_fallback"


def execute_news_database_operation(operation_name, callback):
    """Run one news query against Docker DB, then local fallback if needed."""

    news_database_service, should_close, data_source = open_news_database_service()

    try:
        return callback(news_database_service), data_source

    except Exception:
        if should_close:
            logger.exception(
                "External news database operation failed: %s. Retrying local news tables.",
                operation_name
            )

            return callback(database_service), "local_fallback"

        raise

    finally:
        if should_close:
            news_database_service.close()

"""Helper functions for validating and normalizing identity search criteria and OSINT targets."""

OSINT_ALLOWED_TARGET_FIELDS = {
    "full_name",
    "username",
    "date_of_birth",
    "aadhar_number",
    "pan_number",
    "voter_id_number",
    "driving_license_number",
    "passport_number",
    "phone",
    "phone_number",
    "email",
    "employee_id",
    "department",
    "state",
    "face_image"
}


def osint_targets_from_criteria(criteria):
    """Extract structured OSINT targets from every filled search criterion."""

    targets = []

    for item in criteria or []:

        field = str(item.get("field") or "").strip()
        value = str(item.get("value") or "").strip()

        if field == "face_image":

            continue

        normalized_field = "phone_number" if field == "phone" else field
        target = {
            "key": normalized_field,
            "value": value
        }

        if field in OSINT_ALLOWED_TARGET_FIELDS and value and target not in targets:

            targets.append(target)

    return targets[:10]

"""Validation functions apply strict checks on identity search inputs to prevent bad data and ensure OSINT compatibility."""

def validate_identity_search_criteria(criteria):
    """Validate identity-search field values before DB search or OSINT submit."""

    for item in criteria or []:

        field = str(item.get("field") or "").strip()
        value = str(item.get("value") or "").strip()

        validate_identity_search_value(
            field,
            value
        )


def validate_identity_search_value(
    field,
    value
):
    """Apply strict field-specific validation for identity search inputs."""

    if not value:

        raise ValueError(f"{field.replace('_', ' ').title()} is blank. Please fill the field or remove it.")

    if field == "full_name" and not re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", value):

        raise ValueError("Full Name should contain only letters and spaces")

    if field == "email" and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9])?@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z]{2,})+", value):

        raise ValueError("Email is not in a proper format")

    if field in {
        "phone",
        "phone_number"
    } and not re.fullmatch(r"\d{10}", value):

        raise ValueError("Phone number must be exactly 10 digits without country code or special symbols")

    if field == "username" and not re.fullmatch(r"[A-Za-z0-9@#._]+", value):

        raise ValueError("Username can contain only letters, numbers, @, #, dot, and underscore")


async def build_osint_face_target(uploaded_file):
    """Validate one approved face image and encode it for the OSINT JSON API."""

    if uploaded_file is None:

        return None

    image_bytes = await uploaded_file.read()

    if not image_bytes:

        raise ValueError("Approved Face Image is empty")

    if len(image_bytes) > settings.OSINT_FACE_IMAGE_MAX_BYTES:

        maximum_mb = settings.OSINT_FACE_IMAGE_MAX_BYTES / (1024 * 1024)
        raise ValueError(
            f"Face Image exceeds the {maximum_mb:.1f} MB OSINT upload limit"
        )

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = str(image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("Face Image must be a valid JPG, JPEG, or PNG file") from error

    content_types = {
        "JPEG": "image/jpeg",
        "PNG": "image/png"
    }

    if image_format not in content_types:

        raise ValueError("Face Image must be a valid JPG, JPEG, or PNG file")

    safe_filename = os.path.basename(
        uploaded_file.filename or f"face_image.{image_format.lower()}"
    )

    return {
        "key": "face_image",
        "value": {
            "filename": safe_filename,
            "content_type": content_types[image_format],
            "encoding": "base64",
            "size_bytes": len(image_bytes),
            "base64_data": base64.b64encode(image_bytes).decode("ascii")
        }
    }


def osint_targets_for_storage(targets):
    """Remove image bytes while retaining useful OSINT job audit metadata."""

    stored_targets = []

    for target in targets or []:
        stored_target = dict(target)
        value = stored_target.get("value")

        if stored_target.get("key") == "face_image" and isinstance(value, dict):
            stored_target["value"] = {
                key: item
                for key, item in value.items()
                if key != "base64_data"
            }
            stored_target["value"]["image_attached"] = True

        stored_targets.append(stored_target)

    return stored_targets


def normalize_osint_items(items, face_target=None):
    """Validate approved OSINT items and return provider key/value targets."""

    targets = []

    for item in items or []:

        if isinstance(item, str):

            field = "username"
            value = item.strip()

        else:

            field = str(item.get("field") or "").strip()
            value = str(item.get("value") or "").strip()

        if field not in OSINT_ALLOWED_TARGET_FIELDS:

            raise ValueError(f"Unsupported OSINT field: {field or '-'}")

        validate_identity_search_value(
            field,
            value
        )

        if field == "face_image":

            if not face_target:

                raise ValueError("Approved Face Image file was not uploaded")

            target = face_target

        else:

            normalized_field = "phone_number" if field == "phone" else field
            target = {
                "key": normalized_field,
                "value": value
            }

        if target not in targets:

            targets.append(target)

    if not targets:

        raise ValueError("Select at least one OSINT item before submitting")

    return targets[:10]


def extract_osint_webhook_target_values(payload):
    """Collect searchable target values from provider webhook payloads without job_id."""

    values = []

    def add_value(value):
        normalized_value = str(value or "").strip()

        if normalized_value and normalized_value.lower() not in [
            item.lower()
            for item in values
        ]:

            values.append(normalized_value)

        digits_only = re.sub(
            r"\D",
            "",
            normalized_value
        )

        if len(digits_only) > 10 and digits_only.startswith("91"):

            add_value(digits_only[-10:])

        if normalized_value.startswith("@"):

            add_value(normalized_value[1:])

    for value in payload.get("inputs_processed") or []:

        add_value(value)

    for result_key in (
        "email_results",
        "phone_results",
        "username_results"
    ):

        for result_item in payload.get(result_key) or []:

            add_value(result_item.get("target"))

    for instagram_item in payload.get("instagram_results") or []:

        add_value(instagram_item.get("target"))
        add_value(instagram_item.get("target_username"))

    return values


def ensure_osint_job_normalized(
    job_id,
    job,
    request_database_service
):
    """Return normalized OSINT rows, creating them from raw results when missing."""

    normalized_data = request_database_service.get_normalized_osint_data(job_id)

    if (
        (normalized_data.get("profiles") or normalized_data.get("matches"))
        or not job
        or not job.get("results")
    ):
        return normalized_data

    try:
        logger.info(
            "OSINT normalized data missing, rebuilding from stored result: job_id=%s",
            job_id
        )
        osint_normalizer_service.normalize_and_store(
            job_id,
            {
                "job_id": job_id,
                "status": job.get("status"),
                "results": job.get("results")
            },
            request_database_service
        )
        normalized_data = request_database_service.get_normalized_osint_data(job_id)
        logger.info(
            "OSINT normalized data rebuilt: job_id=%s profiles=%s matches=%s contacts=%s",
            job_id,
            len(normalized_data.get("profiles") or []),
            len(normalized_data.get("matches") or []),
            len(normalized_data.get("contacts") or [])
        )

    except Exception:
        logger.exception(
            "OSINT lazy normalization failed: job_id=%s",
            job_id
        )

    return normalized_data


def osint_avatar_candidates_from_normalized(normalized_data):
    """Collect every normalized OSINT row that can provide an avatar image."""

    candidates = []
    seen = set()

    for section_key in ("profiles", "matches"):
        for row in normalized_data.get(section_key) or []:
            if not row.get("avatar_path") and not row.get("avatar_url"):
                continue

            candidate = dict(row)

            if not candidate.get("profile_url") and candidate.get("url"):
                candidate["profile_url"] = candidate.get("url")

            if not candidate.get("source"):
                candidate["source"] = (
                    "Social Profile"
                    if section_key == "profiles"
                    else "Enriched Match"
                )

            profile_identity = str(
                candidate.get("profile_url")
                or candidate.get("url")
                or ""
            ).strip().lower().rstrip("/")
            avatar_identity = str(
                candidate.get("avatar_url")
                or candidate.get("avatar_path")
                or ""
            ).strip().lower()

            if profile_identity:
                fingerprint = ("profile_url", profile_identity)
            elif avatar_identity:
                fingerprint = ("avatar", avatar_identity)
            else:
                fingerprint = (
                    "metadata",
                    str(candidate.get("platform") or "").strip().lower(),
                    str(candidate.get("target") or "").strip().lower(),
                    str(candidate.get("bio") or candidate.get("extracted_text") or "").strip().lower()
                )

            if fingerprint in seen:
                continue

            seen.add(fingerprint)
            candidates.append(candidate)

    return candidates


def submit_osint_job_background(
    job_id,
    targets
):
    """Submit an OSINT job using a fresh DB connection for the background task."""

    logger.info(
        "OSINT background task started: job_id=%s total_targets=%s",
        job_id,
        len(targets or [])
    )
    background_database_service = DatabaseService()

    try:

        osint_service.submit_scan(
            job_id=job_id,
            targets=targets,
            database_service=background_database_service
        )

    finally:

        background_database_service.close()
        logger.info(
            "OSINT background task finished: job_id=%s",
            job_id
        )


def sync_identity_face_embedding(
    employee_id,
    photo_path
):
    """Generate and persist one identity embedding after a photo change."""

    sync_database_service = DatabaseService()

    try:
        resolved_photo_path = face_service.resolve_database_photo_path(photo_path)
        photo_hash = face_service.photo_fingerprint(resolved_photo_path)
        embedding_payload = face_service.extract_external_embedding(
            resolved_photo_path
        )
        sync_database_service.upsert_face_embedding(
            employee_id=employee_id,
            photo_path=photo_path,
            photo_hash=photo_hash,
            model_name=(
                embedding_payload.get("model_name")
                or settings.FACE_EMBEDDING_MODEL
            ),
            embedding=embedding_payload.get("embedding"),
            face_quality=embedding_payload.get("quality"),
            detection_score=embedding_payload.get("det_score")
        )
        logger.info(
            "Identity face embedding stored: employee_id=%s model=%s",
            employee_id,
            embedding_payload.get("model_name")
        )

    except Exception:
        sync_database_service.delete_face_embedding(employee_id)
        logger.exception(
            "Identity face embedding sync failed: employee_id=%s photo_path=%s",
            employee_id,
            photo_path
        )

    finally:
        sync_database_service.close()


def run_face_search_job_background(
    job_id,
    uploaded_image_path
):
    """Execute one face-search job in the background using a fresh DB connection."""

    logger.info(
        "Face search background task started: job_id=%s uploaded_image_path=%s",
        job_id,
        uploaded_image_path
    )
    background_database_service = DatabaseService()

    try:

        database_people = background_database_service.get_identities_with_photos()
        embedding_coverage = background_database_service.get_face_embedding_coverage()
        embedding_candidates = None

        if embedding_coverage.get("complete"):
            embedding_candidates = (
                background_database_service.get_identity_face_embedding_candidates()
            )

        logger.info(
            "Face search background candidates loaded: job_id=%s total_candidates=%s "
            "ready_embeddings=%s vector_search_enabled=%s",
            job_id,
            len(database_people),
            embedding_coverage.get("ready_embeddings"),
            bool(embedding_candidates)
        )
        background_database_service.mark_face_search_job_processing(
            job_id,
            len(database_people)
        )
        background_database_service.update_face_search_job_progress(
            job_id,
            50,
            (
                "Searching persistent InsightFace embeddings."
                if embedding_candidates
                else "Face comparison is running. Embedding backfill is incomplete."
            )
        )
        face_search_result = face_service.find_best_database_match(
            uploaded_image_path,
            database_people,
            embedding_candidates=embedding_candidates
        )
        payload = {
            "status": "success",
            "total_candidates": len(database_people),
            "matched": face_search_result.get("matched"),
            "best_score": face_search_result.get("best_score"),
            "database_match": face_search_result.get("best_match"),
            "face_verification": face_search_result.get("face_verification"),
            "top_candidates": face_search_result.get("top_candidates", [])
        }
        background_database_service.complete_face_search_job(
            job_id,
            payload,
            len(database_people)
        )
        logger.info(
            "Face search background task completed: job_id=%s matched=%s best_score=%s employee_id=%s",
            job_id,
            payload.get("matched"),
            payload.get("best_score"),
            (payload.get("database_match") or {}).get("employee_id")
        )

    except Exception as error:

        logger.exception(
            "Face search background task failed: job_id=%s",
            job_id
        )
        background_database_service.mark_face_search_job_failed(
            job_id,
            str(error)
        )

    finally:

        background_database_service.close()
        logger.info(
            "Face search background task finished: job_id=%s",
            job_id
        )



def run_document_validation_job_background(
    job_id,
    document_type,
    uploaded_document_path,
    original_filename,
    manual_values
):
    """Execute one document-validation job in the background with a fresh DB connection."""

    logger.info(
        "Document validation background task started: job_id=%s document_type=%s path=%s",
        job_id,
        document_type,
        uploaded_document_path
    )
    background_database_service = DatabaseService()
    background_document_service = DocumentVerificationService(
        file_service,
        ocr_service,
        background_database_service,
        face_service,
        risk_service,
        decision_service
    )

    try:

        background_database_service.mark_document_validation_job_processing(job_id)
        result = background_document_service.verify_saved_file(
            document_type=document_type,
            saved_file_path=uploaded_document_path,
            original_filename=original_filename,
            manual_values=manual_values,
            progress_callback=lambda percent, message: (
                background_database_service.update_document_validation_job_progress(
                    job_id,
                    percent,
                    message
                )
            )
        )
        background_database_service.complete_document_validation_job(
            job_id,
            result
        )
        logger.info(
            "Document validation background task completed: job_id=%s decision=%s employee_id=%s",
            job_id,
            (result.get("decision") or {}).get("status"),
            (result.get("database_match") or {}).get("employee_id")
        )

    except Exception as error:

        logger.exception(
            "Document validation background task failed: job_id=%s",
            job_id
        )
        background_database_service.mark_document_validation_job_failed(
            job_id,
            str(error)
        )

    finally:

        background_database_service.close()
        logger.info(
            "Document validation background task finished: job_id=%s",
            job_id
        )

@app.get("/")
def home():
    """Health-style root endpoint used to confirm the backend is running."""

    return {
        "message": "Identity Search API Running"
    }


@app.get("/health")
def health():
    """Return a lightweight API-only health response."""

    return {
        "status": "ok",
        "service": "identity-search-service",
        "message": "Backend API is running"
    }


@app.get("/health/db")
def health_db():
    """Return PostgreSQL connectivity health."""

    payload, status_code = database_health_payload()

    return JSONResponse(
        status_code=status_code,
        content=payload
    )


@app.get("/health/osint")
def health_osint(

    check_network: bool = Query(False)

):
    """Return OSINT config health and optional network reachability."""

    payload, status_code = osint_health_payload(check_network)

    return JSONResponse(
        status_code=status_code,
        content=payload
    )


@app.get(settings.NEWS_HEALTH_PATH)
def health_news_database():
    """Return optional external news database connectivity health."""

    payload, status_code = news_database_health_payload()

    return JSONResponse(
        status_code=status_code,
        content=payload
    )


@app.get("/health/full")
def health_full(

    check_osint_network: bool = Query(False)

):
    """Return API, DB, news DB, and OSINT health in one response."""

    db_payload, db_status_code = database_health_payload()
    news_db_payload, news_db_status_code = news_database_health_payload()
    osint_payload, osint_status_code = osint_health_payload(
        check_network=check_osint_network
    )
    status_code = 200

    if db_status_code >= 400 or osint_status_code >= 400 or news_db_status_code >= 400:
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "error",
            "service": "identity-search-service",
            "api": {
                "status": "ok"
            },
            "database": db_payload,
            "news_database": news_db_payload,
            "osint": osint_payload
        }
    )

"""Starting of the search-identity route which accepts one field and value to search in the database."""

@app.post("/search-identity")
async def search_identity(

    field: str = Form(...),

    value: str = Form(...)

):
    """Search one identity field in the local `demodataset` table."""

    try:

        logger.info(
            "Identity search requested: field=%s value=%s",
            field,
            value
        )

        validate_identity_search_value(
            field,
            str(value or "").strip()
        )

        results = database_service.search_identity(
            field,
            value
        )

        logger.info(
            "Identity search completed: field=%s total_matches=%s",
            field,
            len(results)
        )

        return JSONResponse(

            content={

                "status": "success",

                "total_matches": len(results),

                "results": results
            }
        )

    except ValueError as e:

        logger.exception("Identity search validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Identity search failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )
"""Ending of the search-identity route which accepts one field and value to search in the database."""

@app.post("/search-identity-advanced")
async def search_identity_advanced(

    background_tasks: BackgroundTasks,

    criteria_json: str = Form(...),

    submit_osint: str = Form("true")

):
    """Search multiple identity fields and optionally queue an OSINT job."""

    try:

        criteria = json.loads(criteria_json)

        if not isinstance(criteria, list):

            raise ValueError("Search criteria must be a list")

        validate_identity_search_criteria(criteria)

        logger.info(
            "Advanced identity search requested: total_criteria=%s",
            len(criteria)
        )

        results = database_service.search_identity_multi(criteria)
        osint_job = None
        osint_targets = osint_targets_from_criteria(criteria)
        should_submit_osint = str(submit_osint or "true").lower() in {
            "1",
            "true",
            "yes"
        }

        if should_submit_osint and osint_targets and osint_service.is_configured():

            logger.info(
                "OSINT job creation requested from advanced search: total_targets=%s",
                len(osint_targets)
            )
            osint_job = database_service.create_osint_job(
                targets=osint_targets
            )
            job_id = osint_job.get("job_id")
            logger.info(
                "OSINT job created from advanced search: job_id=%s db_status=%s",
                job_id,
                osint_job.get("status")
            )
            background_tasks.add_task(
                submit_osint_job_background,
                job_id,
                osint_targets
            )
            logger.info(
                "OSINT job scheduled for engine submission: job_id=%s",
                job_id
            )

        logger.info(
            "Advanced identity search completed: total_matches=%s osint_job_id=%s",
            len(results),
            osint_job.get("job_id") if osint_job else None
        )

        return JSONResponse(

            content={

                "status": "success",

                "total_matches": len(results),

                "results": results,

                "osint_job": osint_job,

                "osint_enabled": osint_service.is_configured()
            }
        )

    except ValueError as e:

        logger.exception("Advanced identity search validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Advanced identity search failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/api/v1/osint/jobs")
async def submit_approved_osint_job(

    background_tasks: BackgroundTasks,

    targets_json: str = Form(...),

    face_image: UploadFile = File(None)

):
    """Create an OSINT job only after the dashboard user approves targets."""

    try:

        if not osint_service.is_configured():

            raise ValueError(osint_service.configuration_message())

        items = json.loads(targets_json)

        if not isinstance(items, list):

            raise ValueError("OSINT targets must be a list")

        has_face_item = any(
            str(item.get("field") or "").strip() == "face_image"
            for item in items
            if isinstance(item, dict)
        )

        if face_image is not None and not has_face_item:

            raise ValueError("Face Image file was provided without an approved face_image target")

        face_target = await build_osint_face_target(face_image) if has_face_item else None
        osint_targets = normalize_osint_items(
            items,
            face_target=face_target
        )
        logger.info(
            "Approved OSINT job creation requested: total_targets=%s",
            len(osint_targets)
        )
        osint_job = database_service.create_osint_job(
            targets=osint_targets_for_storage(osint_targets)
        )
        job_id = osint_job.get("job_id")
        logger.info(
            "Approved OSINT job created: job_id=%s db_status=%s",
            job_id,
            osint_job.get("status")
        )

        background_tasks.add_task(
            submit_osint_job_background,
            job_id,
            osint_targets
        )
        logger.info(
            "Approved OSINT job scheduled for engine submission: job_id=%s",
            job_id
        )

        logger.info(
            "Approved OSINT job queued: job_id=%s total_targets=%s",
            job_id,
            len(osint_targets)
        )

        return JSONResponse(
            content={
                "status": "success",
                "message": "OSINT job queued after user approval",
                "osint_job": osint_job
            }
        )

    except (ValueError, json.JSONDecodeError) as e:

        logger.exception("Approved OSINT job validation failed")

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Approved OSINT job submission failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )


@app.get("/api/v1/osint/jobs/{job_id}")
async def get_osint_job(

    job_id: str

):
    """Return one OSINT job for Streamlit polling and final-result display."""

    request_database_service = DatabaseService()

    try:

        request_database_service.mark_stale_osint_jobs_failed(
            settings.OSINT_JOB_STALE_MINUTES
        )
        job = request_database_service.get_osint_job(job_id)

        if not job:

            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"OSINT job not found: {job_id}"
                }
            )

        job["normalized"] = ensure_osint_job_normalized(
            job_id,
            job,
            request_database_service
        )

        return JSONResponse(
            content={
                "status": "success",
                "job": job
            }
        )

    except Exception as e:

        logger.exception("OSINT job lookup failed: job_id=%s", job_id)

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    finally:

        request_database_service.close()


@app.post("/api/v1/jobs/face-search")
async def submit_face_search_job(

    background_tasks: BackgroundTasks,

    image: UploadFile = File(...)

):
    """Create a background face-search job and return immediately with a job ID."""

    request_database_service = DatabaseService()

    try:

        logger.info(
            "Face search async job creation requested: filename=%s",
            image.filename
        )
        saved_file_path = file_service.save_upload(image)
        face_job = request_database_service.create_face_search_job(
            saved_file_path
        )
        job_id = face_job.get("job_id")
        background_tasks.add_task(
            run_face_search_job_background,
            job_id,
            saved_file_path
        )
        logger.info(
            "Face search async job queued: job_id=%s uploaded_image_path=%s",
            job_id,
            saved_file_path
        )

        return JSONResponse(
            content={
                "status": "success",
                "message": "Face search queued successfully",
                "job": face_job
            }
        )

    except ValueError as e:

        logger.exception("Face search async validation failed")

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Face search async job submission failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    finally:

        request_database_service.close()


@app.get("/api/v1/jobs/face-search/{job_id}")
async def get_face_search_job(

    job_id: str

):
    """Return one background face-search job for dashboard polling."""

    request_database_service = DatabaseService()

    try:

        request_database_service.mark_stale_face_search_jobs_failed(
            settings.FACE_SEARCH_JOB_STALE_MINUTES
        )
        job = request_database_service.get_face_search_job(job_id)

        if not job:

            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"Face search job not found: {job_id}"
                }
            )

        return JSONResponse(
            content={
                "status": "success",
                "job": job
            }
        )

    except Exception as e:

        logger.exception("Face search job lookup failed: job_id=%s", job_id)

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    finally:

        request_database_service.close()


def resolve_osint_avatar_for_face_check(job_id, profile):
    """Return a local avatar path, downloading remote URLs when possible."""

    project_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            ".."
        )
    )
    avatar_path = profile.get("avatar_path")

    if avatar_path:
        candidate_path = avatar_path

        if not os.path.isabs(candidate_path):
            candidate_path = os.path.join(
                project_root,
                avatar_path.replace("/", os.sep)
            )

        if os.path.exists(candidate_path) and is_valid_osint_avatar_file(candidate_path):
            return candidate_path, None

    avatar_url = str(profile.get("avatar_url") or "").strip()

    if not avatar_url.startswith(("http://", "https://")):
        return None, "No decoded avatar image or downloadable avatar URL was available"

    try:
        response = requests.get(
            avatar_url,
            headers={
                "User-Agent": "identity-search-service/1.0"
            },
            timeout=15
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()

        if "image" not in content_type:
            return None, f"Avatar URL did not return an image: {content_type or 'unknown content type'}"

        if len(response.content) > 5 * 1024 * 1024:
            return None, "Avatar image is larger than 5 MB"

        try:
            extension = avatar_extension_from_bytes(response.content)
        except ValueError as error:
            return None, str(error)

        image_dir = os.path.join(
            project_root,
            "backend",
            "uploads",
            "osint_images"
        )
        os.makedirs(
            image_dir,
            exist_ok=True
        )
        safe_platform = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(profile.get("platform") or "platform")
        ).strip("_")
        file_name = f"{job_id}_{safe_platform}_avatar_{uuid4().hex[:8]}.{extension}"
        avatar_file_path = os.path.join(
            image_dir,
            file_name
        )

        with open(avatar_file_path, "wb") as avatar_file:
            avatar_file.write(response.content)

        return avatar_file_path, None

    except Exception as error:
        return None, f"Avatar URL could not be downloaded: {error}"


def avatar_extension_from_bytes(image_bytes):
    """Validate downloaded avatar bytes and return a safe extension."""

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.verify()
            image_format = (image.format or "").upper()
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise ValueError("Avatar bytes are not a renderable image") from error

    extension_map = {
        "JPEG": "jpg",
        "JPG": "jpg",
        "PNG": "png",
        "WEBP": "webp"
    }
    extension = extension_map.get(image_format)

    if not extension:
        raise ValueError(f"Unsupported avatar image format: {image_format or 'unknown'}")

    return extension


def is_valid_osint_avatar_file(image_path):
    """Return True only when a stored OSINT avatar is a real image file."""

    try:
        with Image.open(image_path) as image:
            image.verify()
            image_format = (image.format or "").upper()
    except (OSError, UnidentifiedImageError, ValueError):
        return False

    return image_format in {"JPEG", "JPG", "PNG", "WEBP"}


@app.post("/api/v1/osint/jobs/{job_id}/verify-avatars")
async def verify_osint_avatars(

    job_id: str,

    verification_request: dict = Body(None)

):
    """Compare normalized OSINT avatar images with registered database photos."""

    request_database_service = DatabaseService()

    try:
        job = request_database_service.get_osint_job(job_id)

        if not job:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"OSINT job not found: {job_id}"
                }
            )

        normalized_data = ensure_osint_job_normalized(
            job_id,
            job,
            request_database_service
        )
        profiles = osint_avatar_candidates_from_normalized(normalized_data)
        approved_avatars = (verification_request or {}).get("approved_avatars") or []

        if approved_avatars:
            profiles = approved_avatars

        database_people = request_database_service.get_identities_with_photos()
        embedding_coverage = request_database_service.get_face_embedding_coverage()
        embedding_candidates = (
            request_database_service.get_identity_face_embedding_candidates()
            if embedding_coverage.get("complete")
            else None
        )
        verification_rows = []

        for profile in profiles:
            avatar_path, avatar_error = resolve_osint_avatar_for_face_check(
                job_id,
                profile
            )

            if avatar_error:
                verification_rows.append(
                    {
                        "platform": profile.get("platform"),
                        "target": profile.get("target"),
                        "profile_url": profile.get("profile_url") or profile.get("url"),
                        "avatar_url": profile.get("avatar_url"),
                        "avatar_path": profile.get("avatar_path"),
                        "matched": False,
                        "best_score": 0.0,
                        "database_match": None,
                        "message": avatar_error
                    }
                )
                continue

            face_result = face_service.find_best_database_match(
                avatar_path,
                database_people,
                embedding_candidates=embedding_candidates
            )
            verification_rows.append(
                {
                    "platform": profile.get("platform"),
                    "target": profile.get("target"),
                    "profile_url": profile.get("profile_url") or profile.get("url"),
                    "avatar_url": profile.get("avatar_url"),
                    "avatar_path": profile.get("avatar_path") or avatar_path,
                    "matched": face_result.get("matched"),
                    "best_score": face_result.get("best_score"),
                    "score_gap": face_result.get("score_gap"),
                    "database_match": face_result.get("best_match"),
                    "face_verification": face_result.get("face_verification"),
                    "message": (
                        "Face matched with database identity"
                        if face_result.get("matched")
                        else (face_result.get("face_verification") or {}).get("error")
                    )
                }
            )

        matched_rows = [
            row
            for row in verification_rows
            if row.get("matched")
        ]
        matched_rows.sort(
            key=lambda row: row.get("best_score") or 0.0,
            reverse=True
        )
        best_row = matched_rows[0] if matched_rows else None
        verified_identity = best_row.get("database_match") if best_row else None

        if verified_identity:
            conclusion = {
                "decision": "VERIFIED",
                "summary": (
                    "DB + OSINT verified. At least one OSINT avatar matched a "
                    "registered database face."
                )
            }
        elif verification_rows:
            conclusion = {
                "decision": "NOT VERIFIED",
                "summary": (
                    "OSINT profiles were found, but no avatar confidently matched "
                    "a registered database face."
                )
            }
        else:
            conclusion = {
                "decision": "NO AVATAR",
                "summary": "No OSINT avatar image was available for face verification."
            }

        return JSONResponse(
            content={
                "status": "success",
                "job_id": job_id,
                "verified_identity": verified_identity,
                "conclusion": conclusion,
                "avatar_verifications": verification_rows,
                "normalized": normalized_data
            }
        )

    except Exception as e:
        logger.exception("OSINT avatar verification failed: job_id=%s", job_id)

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    finally:
        request_database_service.close()


@app.post(settings.NEWS_WEBHOOK_PATH)
async def receive_news_update(

    payload: dict = Body(
        ...,
        example={
            "batch_id": "NEWS-20260702-001",
            "status": "completed",
            "completed_at": "2026-07-02T10:30:00+05:30",
            "counts": {
                "clusters": 12,
                "articles": 240,
                "cluster_entities": 90,
                "article_entities": 820
            }
        }
    ),

    x_news_webhook_secret: str = Header(
        "",
        alias=settings.NEWS_WEBHOOK_HEADER_NAME
    )

):
    """Acknowledge a completed/failed scraper batch and verify remote data."""

    request_database_service = None
    remote_news_database_service = None
    batch_id = str(payload.get("batch_id") or "").strip()

    try:

        expected_token = str(settings.NEWS_WEBHOOK_TOKEN or "")

        if not expected_token:

            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": "NEWS_WEBHOOK_TOKEN is not configured"
                }
            )

        if not hmac.compare_digest(x_news_webhook_secret, expected_token):

            logger.warning(
                "News webhook rejected: reason=invalid_token batch_id=%s",
                batch_id or "-"
            )

            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "message": "Invalid news webhook token"
                }
            )

        payload_size = len(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )

        if payload_size > settings.NEWS_WEBHOOK_MAX_PAYLOAD_BYTES:

            return JSONResponse(
                status_code=413,
                content={
                    "status": "error",
                    "message": "News webhook payload is too large"
                }
            )

        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", batch_id):

            raise ValueError(
                "batch_id is required and may contain letters, numbers, dot, underscore, colon, or hyphen"
            )

        normalized_status = str(payload.get("status") or "").strip().upper()

        if normalized_status not in {"COMPLETED", "FAILED"}:

            raise ValueError("status must be completed or failed")

        counts = payload.get("counts") or {}

        if not isinstance(counts, dict):

            raise ValueError("counts must be a JSON object")

        for count_name, count_value in counts.items():

            if isinstance(count_value, bool) or not isinstance(count_value, int) or count_value < 0:

                raise ValueError(
                    f"counts.{count_name} must be a non-negative integer"
                )

        completed_at = payload.get("completed_at")

        if completed_at:

            try:
                datetime.fromisoformat(
                    str(completed_at).replace("Z", "+00:00")
                )
            except ValueError as error:
                raise ValueError(
                    "completed_at must be an ISO-8601 datetime"
                ) from error

        request_database_service = DatabaseService()
        database_snapshot = None
        error_message = payload.get("error") or payload.get("message")

        logger.info(
            "News webhook received: batch_id=%s status=%s reported_counts=%s",
            batch_id,
            normalized_status,
            counts
        )

        if normalized_status == "COMPLETED":

            if not NewsDatabaseService.is_configured():

                raise ConnectionError(
                    "NEWS_DATABASE_URL is not configured; remote batch cannot be verified"
                )

            try:
                remote_news_database_service = NewsDatabaseService()
                database_snapshot = remote_news_database_service.get_data_snapshot()
            except Exception as error:
                failure_message = (
                    "Remote news database verification failed: "
                    f"{error}"
                )
                request_database_service.save_news_ingestion_event(
                    batch_id=batch_id,
                    status="FAILED",
                    payload=payload,
                    reported_counts=counts,
                    error_message=failure_message,
                    engine_completed_at=completed_at
                )
                logger.exception(
                    "News webhook failed: batch_id=%s reason=remote_database_unavailable",
                    batch_id
                )

                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "batch_id": batch_id,
                        "message": failure_message
                    }
                )

        event = request_database_service.save_news_ingestion_event(
            batch_id=batch_id,
            status=normalized_status,
            payload=payload,
            reported_counts=counts,
            database_snapshot=database_snapshot,
            source=str(payload.get("source") or "news-intelligence-engine"),
            error_message=error_message if normalized_status == "FAILED" else None,
            engine_completed_at=completed_at
        )

        logger.info(
            "News webhook stored: batch_id=%s status=%s database_snapshot=%s",
            batch_id,
            normalized_status,
            database_snapshot
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "News batch notification accepted",
                "batch": event
            }
        )

    except ValueError as error:

        logger.warning(
            "News webhook validation failed: batch_id=%s error=%s",
            batch_id or "-",
            error
        )

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(error)
            }
        )

    except Exception as error:

        logger.exception("News webhook processing failed: batch_id=%s", batch_id or "-")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(error)
            }
        )

    finally:

        if remote_news_database_service:
            remote_news_database_service.close()

        if request_database_service:
            request_database_service.close()


@app.get(settings.NEWS_SYNC_STATUS_PATH)
async def get_latest_news_sync_status(

    include_live_snapshot: bool = Query(False)

):
    """Return the latest accepted news batch and optional current DB totals."""

    request_database_service = None
    remote_news_database_service = None

    try:
        request_database_service = DatabaseService()
        event = request_database_service.get_latest_news_ingestion_event()
        live_snapshot = None
        snapshot_status = "not_requested"
        snapshot_error = None

        if include_live_snapshot:

            if NewsDatabaseService.is_configured():

                try:
                    remote_news_database_service = NewsDatabaseService()
                    live_snapshot = remote_news_database_service.get_data_snapshot()
                    snapshot_status = "available"
                except Exception as error:
                    snapshot_status = "unavailable"
                    snapshot_error = str(error)
                    logger.warning(
                        "Latest news live snapshot unavailable: %s",
                        error
                    )

            else:
                snapshot_status = "not_configured"

        return JSONResponse(
            content={
                "status": "success",
                "latest_batch": event,
                "live_snapshot": live_snapshot,
                "snapshot_status": snapshot_status,
                "snapshot_error": snapshot_error
            }
        )

    except Exception as error:
        logger.exception("Latest news sync status lookup failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(error)
            }
        )

    finally:
        if remote_news_database_service:
            remote_news_database_service.close()

        if request_database_service:
            request_database_service.close()


@app.get("/api/v1/news/clusters/top")
async def get_top_news_clusters(

    limit: int = Query(10, ge=1, le=50)

):
    """Return the top news clusters for the dashboard overview."""

    try:

        clusters, data_source = execute_news_database_operation(
            "top news clusters",
            lambda news_database_service: news_database_service.list_top_news_clusters(limit)
        )

        return JSONResponse(
            content={
                "status": "success",
                "total_clusters": len(clusters),
                "data_source": data_source,
                "clusters": clusters
            }
        )

    except Exception as e:

        logger.exception("Top news cluster lookup failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

@app.get("/api/v1/news/search")
async def search_news(

    q: str = Query(..., min_length=1),

    limit: int = Query(10, ge=1, le=50)

):
    """Search news clusters, articles, and entities by a user topic."""

    try:

        clusters, data_source = execute_news_database_operation(
            "news search",
            lambda news_database_service: news_database_service.search_news(
                q,
                limit
            )
        )

        return JSONResponse(
            content={
                "status": "success",
                "query": q,
                "total_clusters": len(clusters),
                "data_source": data_source,
                "clusters": clusters
            }
        )

    except Exception as e:

        logger.exception("News search failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

@app.get("/api/v1/news/topics")
async def get_common_news_topics(

    limit: int = Query(500, ge=1, le=500)

):
    """Return common searchable topics extracted from the news entity tables."""

    try:

        topics, data_source = execute_news_database_operation(
            "common news topics",
            lambda news_database_service: news_database_service.list_common_news_topics(limit)
        )

        return JSONResponse(
            content={
                "status": "success",
                "total_topics": len(topics),
                "data_source": data_source,
                "topics": topics
            }
        )

    except Exception as e:

        logger.exception("Common news topic lookup failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

@app.get("/api/v1/news/clusters/{cluster_id}")
async def get_news_cluster_detail(

    cluster_id: str

):
    """Return one news cluster with sources, entities, and linked articles."""

    try:

        cluster, data_source = execute_news_database_operation(
            "news cluster detail",
            lambda news_database_service: news_database_service.get_news_cluster_detail(cluster_id)
        )

        if not cluster:

            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"News cluster not found: {cluster_id}"
                }
            )

        return JSONResponse(
            content={
                "status": "success",
                "data_source": data_source,
                "cluster": cluster
            }
        )

    except Exception as e:

        logger.exception("News cluster detail lookup failed: cluster_id=%s", cluster_id)

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

@app.post("/api/webhooks/osint-results")
async def receive_osint_results(

    payload: dict = Body(
        ...,
        example={
            "job_id": "JOBDUMMY01",
            "status": "completed",
            "results": {
                "profile_url": "https://www.instagram.com/ad018jan/",
                "facebook_results": [
                    {
                        "platform": "Facebook",
                        "profile_url": "https://www.facebook.com/ad018jan",
                        "status": "found"
                    }
                ]
            }
        }
    ),

    webhook_token: str = Query(""),

    x_webhook_secret: str = Header("")

):
    """Receive the OSINT provider webhook and store the completed job result."""

    request_database_service = DatabaseService()

    try:

        expected_token = settings.OSINT_WEBHOOK_TOKEN
        received_token = x_webhook_secret or webhook_token

        if expected_token and not hmac.compare_digest(
            received_token,
            expected_token
        ):

            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "message": "Invalid OSINT webhook token"
                }
            )

        job_id = str(
            payload.get("job_id")
            or ""
        ).strip()
        logger.info(
            "OSINT webhook received: job_id=%s status=%s payload_keys=%s",
            job_id or "-",
            payload.get("status"),
            list(payload.keys())
        )

        if not job_id:

            target_values = extract_osint_webhook_target_values(payload)
            matched_job = request_database_service.find_latest_osint_job_by_targets(
                target_values
            )

            if matched_job:

                job_id = matched_job.get("job_id")
                logger.info(
                    "OSINT webhook matched without job_id: job_id=%s matched_targets=%s",
                    job_id,
                    target_values
                )

            else:

                logger.error(
                    "OSINT webhook missing job_id and no active job matched: target_values=%s",
                    target_values
                )

                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": (
                            "Webhook payload must include job_id or match an active "
                            "OSINT job target"
                        )
                    }
                )

        completed_job = request_database_service.complete_osint_job(
            job_id=job_id,
            status=payload.get("status"),
            result_payload=payload.get("results") or payload
        )

        if not completed_job:

            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": (
                        "No OSINT job found for "
                        f"job_id={job_id or '-'}"
                    )
                }
            )

        logger.info(
            "OSINT webhook stored: job_id=%s db_status=%s result_saved=%s",
            completed_job.get("job_id"),
            completed_job.get("status"),
            completed_job.get("results") is not None
        )

        try:

            normalized_counts = osint_normalizer_service.normalize_and_store(
                job_id=completed_job.get("job_id"),
                payload=payload,
                database_service=request_database_service
            )
            logger.info(
                "OSINT webhook normalized: job_id=%s counts=%s",
                completed_job.get("job_id"),
                normalized_counts
            )

        except Exception:

            logger.exception(
                "OSINT normalization failed after raw result storage: job_id=%s",
                completed_job.get("job_id")
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "OSINT result stored successfully",
                "job_id": completed_job.get("job_id")
            }
        )

    except ValueError as e:

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("OSINT webhook processing failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    finally:

        request_database_service.close()


@app.post("/api/v1/jobs/document-validation")
async def submit_document_validation_job(

    background_tasks: BackgroundTasks,

    document_type: str = Form(...),

    document: UploadFile = File(...),

    aadhar_number: str = Form(""),

    pan_number: str = Form(""),

    voter_id_number: str = Form(""),

    driving_license_number: str = Form(""),

    passport_number: str = Form("")

):
    """Create a background document-validation job and return immediately."""

    request_database_service = DatabaseService()

    try:

        logger.info(
            "Document validation async job creation requested: document_type=%s filename=%s",
            document_type,
            document.filename
        )
        saved_file_path = file_service.save_upload(document)
        manual_values = {
            "aadhar_number": aadhar_number,
            "pan_number": pan_number,
            "voter_id_number": voter_id_number,
            "driving_license_number": driving_license_number,
            "passport_number": passport_number
        }
        document_job = request_database_service.create_document_validation_job(
            document_type=document_type,
            uploaded_document_path=saved_file_path,
            original_filename=document.filename,
            manual_values=manual_values
        )
        job_id = document_job.get("job_id")
        background_tasks.add_task(
            run_document_validation_job_background,
            job_id,
            document_type,
            saved_file_path,
            document.filename,
            manual_values
        )
        logger.info(
            "Document validation async job queued: job_id=%s document_type=%s path=%s",
            job_id,
            document_type,
            saved_file_path
        )

        return JSONResponse(
            content={
                "status": "success",
                "message": "Document validation queued successfully",
                "job": document_job
            }
        )

    except ValueError as e:

        logger.exception("Document validation async validation failed")

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Document validation async job submission failed")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    finally:

        request_database_service.close()


@app.get("/api/v1/jobs/document-validation/{job_id}")
async def get_document_validation_job(

    job_id: str

):
    """Return one background document-validation job for dashboard polling."""

    request_database_service = DatabaseService()

    try:

        request_database_service.mark_stale_document_validation_jobs_failed(
            settings.DOCUMENT_VALIDATION_JOB_STALE_MINUTES
        )
        job = request_database_service.get_document_validation_job(job_id)

        if not job:

            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"Document validation job not found: {job_id}"
                }
            )

        return JSONResponse(
            content={
                "status": "success",
                "job": job
            }
        )

    except Exception as e:

        logger.exception("Document validation job lookup failed: job_id=%s", job_id)

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )

    finally:

        request_database_service.close()

@app.post("/validate-id")
async def validate_id(

    document_type: str = Form(...),

    document: UploadFile = File(...),

    aadhar_number: str = Form(""),

    pan_number: str = Form(""),

    voter_id_number: str = Form(""),

    driving_license_number: str = Form(""),

    passport_number: str = Form("")

):
    """Validate one uploaded ID document through OCR, DB match, face, and risk."""

    try:

        result = document_verification_service.verify(
            document_type=document_type,
            document=document,
            manual_values={
                "aadhar_number": aadhar_number,
                "pan_number": pan_number,
                "voter_id_number": voter_id_number,
                "driving_license_number": driving_license_number,
                "passport_number": passport_number
            }
        )

        return JSONResponse(

            content=result
        )

    except ValueError as e:

        logger.exception("Document verification validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Document verification failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/extract-document-fields")
async def extract_document_fields(

    document_type: str = Form(...),

    document: UploadFile = File(...)

):
    """Run OCR only and return extracted fields for admin-create autofill."""

    try:

        logger.info(
            "Document field extraction started: document_type=%s filename=%s",
            document_type,
            document.filename
        )

        saved_file_path = file_service.save_upload(document)

        extracted_text = ocr_service.extract_text(
            saved_file_path,
            document_type
        )

        extracted_data = ocr_service.extract_identity_fields(
            document_type,
            extracted_text
        )

        logger.info(
            "Document field extraction completed: document_type=%s name=%s aadhaar=%s pan=%s voter_id=%s driving_license=%s passport=%s",
            extracted_data.get("document_type"),
            extracted_data.get("full_name"),
            extracted_data.get("aadhar_number"),
            extracted_data.get("pan_number"),
            extracted_data.get("voter_id_number"),
            extracted_data.get("driving_license_number"),
            extracted_data.get("passport_number")
        )

        return JSONResponse(

            content={

                "status": "success",

                "extracted_data": extracted_data,

                "uploaded_document_path": saved_file_path
            }
        )

    except ValueError as e:

        logger.exception("Document field extraction validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Document field extraction failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.get("/admin/identities")
async def admin_list_identities(

    limit: int = Query(100)

):
    """Return recent identity records for the admin dashboard table."""

    try:

        identities = database_service.list_identities(limit)

        return JSONResponse(

            content={

                "status": "success",

                "total_records": len(identities),

                "records": identities
            }
        )

    except Exception as e:

        logger.exception("Admin identity list failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.get("/admin/identities/{employee_id}")
async def admin_get_identity(

    employee_id: str

):
    """Fetch one identity so the update form can be populated by employee ID."""

    try:

        identity = database_service.get_identity_by_employee_id(employee_id)

        if not identity:

            return JSONResponse(

                status_code=404,

                content={

                    "status": "error",

                    "message": f"Identity not found: {employee_id}"
                }
            )

        return JSONResponse(

            content={

                "status": "success",

                "record": identity
            }
        )

    except Exception as e:

        logger.exception("Admin identity fetch failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/admin/identities")
async def admin_create_identity(

    background_tasks: BackgroundTasks,

    employee_id: str = Form(...),

    full_name: str = Form(...),

    date_of_birth: str = Form(""),

    aadhar_number: str = Form(""),

    pan_number: str = Form(""),

    voter_id_number: str = Form(""),

    driving_license_number: str = Form(""),

    passport_number: str = Form(""),

    phone_number: str = Form(""),

    email: str = Form(""),

    department: str = Form(""),

    state: str = Form(""),

    photo: UploadFile = File(None)

):
    """Create a new identity record from admin form fields and optional photo."""

    try:

        photo_path = None

        if photo and photo.filename:

            photo_path = file_service.save_employee_photo(
                photo,
                employee_id
            )

        created_identity = database_service.create_identity_admin(
            {
                "employee_id": employee_id,
                "full_name": full_name,
                "date_of_birth": date_of_birth,
                "aadhar_number": aadhar_number,
                "pan_number": pan_number,
                "voter_id_number": voter_id_number,
                "driving_license_number": driving_license_number,
                "passport_number": passport_number,
                "phone_number": phone_number,
                "email": email,
                "department": department,
                "state": state,
                "photo_path": photo_path
            }
        )

        if photo_path:
            background_tasks.add_task(
                sync_identity_face_embedding,
                created_identity.get("employee_id"),
                created_identity.get("photo_path")
            )
        return JSONResponse(

            content={

                "status": "success",

                "message": "Identity created successfully",

                "record": created_identity
            }
        )

    except ValueError as e:

        logger.exception("Admin identity create validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Admin identity create failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/admin/identities/{employee_id}/update")
async def admin_update_identity(

    employee_id: str,

    background_tasks: BackgroundTasks,

    full_name: str = Form(...),

    date_of_birth: str = Form(""),

    aadhar_number: str = Form(""),

    pan_number: str = Form(""),

    voter_id_number: str = Form(""),

    driving_license_number: str = Form(""),

    passport_number: str = Form(""),

    phone_number: str = Form(""),

    email: str = Form(""),

    department: str = Form(""),

    state: str = Form(""),

    photo: UploadFile = File(None)

):
    """Update an existing identity record and optionally replace its photo."""

    try:

        photo_path = None

        if photo and photo.filename:

            photo_path = file_service.save_employee_photo(
                photo,
                employee_id
            )

        updated_identity = database_service.update_identity_admin(
            employee_id,
            {
                "full_name": full_name,
                "date_of_birth": date_of_birth,
                "aadhar_number": aadhar_number,
                "pan_number": pan_number,
                "voter_id_number": voter_id_number,
                "driving_license_number": driving_license_number,
                "passport_number": passport_number,
                "phone_number": phone_number,
                "email": email,
                "department": department,
                "state": state,
                "photo_path": photo_path
            }
        )

        if photo_path:
            background_tasks.add_task(
                sync_identity_face_embedding,
                updated_identity.get("employee_id"),
                updated_identity.get("photo_path")
            )
        return JSONResponse(

            content={

                "status": "success",

                "message": "Identity updated successfully",

                "record": updated_identity
            }
        )

    except ValueError as e:

        logger.exception("Admin identity update validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Admin identity update failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/admin/identities/{employee_id}/delete")
async def admin_delete_identity(

    employee_id: str

):
    """Delete an identity by employee ID and return the deleted record."""

    try:

        deleted_identity = database_service.delete_identity_admin(employee_id)

        return JSONResponse(

            content={

                "status": "success",

                "message": "Identity deleted successfully",

                "record": deleted_identity
            }
        )

    except ValueError as e:

        logger.exception("Admin identity delete validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Admin identity delete failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.get("/manual-review-cases")
async def list_manual_review_cases(

    status: str = Query("PENDING")

):
    """List manual review cases for the reviewer dashboard tab."""

    try:

        logger.info("Manual review case list requested: status=%s", status)

        cases = database_service.list_manual_review_cases(status)

        logger.info(
            "Manual review case list completed: status=%s total_cases=%s",
            status,
            len(cases)
        )

        return JSONResponse(

            content={

                "status": "success",

                "total_cases": len(cases),

                "cases": cases
            }
        )

    except Exception as e:

        logger.exception("Manual review case list failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/manual-review-cases/{case_id}/decision")
async def update_manual_review_case(

    case_id: int,

    reviewer_decision: str = Form(...),

    reviewer_notes: str = Form("")

):
    """Persist a reviewer decision and notes for one manual-review case."""

    try:

        logger.info(
            "Manual review decision requested: case_id=%s reviewer_decision=%s",
            case_id,
            reviewer_decision
        )

        review_case = database_service.update_manual_review_case(
            case_id,
            reviewer_decision,
            reviewer_notes
        )

        logger.info(
            "Manual review decision completed: case_id=%s status=%s",
            case_id,
            review_case.get("status")
        )

        return JSONResponse(

            content={

                "status": "success",

                "message": f"Manual review case marked as {review_case.get('status')}",

                "case": review_case
            }
        )

    except ValueError as e:

        logger.exception("Manual review decision validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Manual review decision failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/search-by-face")
async def search_by_face(

    image: UploadFile = File(...)

):
    """Search all database profile photos for the uploaded face image."""

    try:

        logger.info("Face search started: filename=%s", image.filename)

        saved_file_path = file_service.save_upload(image)

        logger.info("Face search image saved: path=%s", saved_file_path)

        database_people = database_service.get_identities_with_photos()
        embedding_coverage = database_service.get_face_embedding_coverage()
        embedding_candidates = (
            database_service.get_identity_face_embedding_candidates()
            if embedding_coverage.get("complete")
            else None
        )

        logger.info(
            "Face search database candidates loaded: total_candidates=%s",
            len(database_people)
        )

        face_search_result = face_service.find_best_database_match(
            saved_file_path,
            database_people,
            embedding_candidates=embedding_candidates
        )

        logger.info(
            "Face search completed: matched=%s best_score=%s employee_id=%s",
            face_search_result.get("matched"),
            face_search_result.get("best_score"),
            (face_search_result.get("best_match") or {}).get("employee_id")
        )

        return JSONResponse(

            content={

                "status": "success",

                "total_candidates": len(database_people),

                "matched": face_search_result.get("matched"),

                "best_score": face_search_result.get("best_score"),

                "database_match": face_search_result.get("best_match"),

                "face_verification": face_search_result.get("face_verification"),

                "top_candidates": face_search_result.get("top_candidates", [])
            }
        )

    except ValueError as e:

        logger.exception("Face search validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Face search failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )


@app.post("/register-identity")
async def register_identity(

    background_tasks: BackgroundTasks,

    employee_id: str = Form(...),

    full_name: str = Form(...),

    date_of_birth: str = Form(""),

    aadhar_number: str = Form(""),

    pan_number: str = Form(""),

    voter_id_number: str = Form(""),

    driving_license_number: str = Form(""),

    passport_number: str = Form(""),

    phone_number: str = Form(""),

    email: str = Form(""),

    department: str = Form(""),

    state: str = Form(""),

    photo: UploadFile = File(...)

):
    """Register a new identity with a required profile photo."""

    try:

        logger.info(
            "Identity registration started: employee_id=%s full_name=%s photo=%s",
            employee_id,
            full_name,
            photo.filename
        )

        photo_path = file_service.save_employee_photo(
            photo,
            employee_id
        )

        logger.info(
            "Identity registration photo saved: employee_id=%s photo_path=%s",
            employee_id,
            photo_path
        )

        registered_user = database_service.register_identity(
            {
                "employee_id": employee_id.strip(),
                "full_name": full_name.strip(),
                "date_of_birth": date_of_birth.strip(),
                "aadhar_number": aadhar_number.strip(),
                "pan_number": pan_number.strip(),
                "voter_id_number": voter_id_number.strip(),
                "driving_license_number": driving_license_number.strip(),
                "passport_number": passport_number.strip(),
                "phone_number": phone_number.strip(),
                "email": email.strip(),
                "department": department.strip(),
                "state": state.strip(),
                "photo_path": photo_path
            }
        )

        background_tasks.add_task(
            sync_identity_face_embedding,
            registered_user.get("employee_id"),
            registered_user.get("photo_path")
        )
        logger.info(
            "Identity registration completed: employee_id=%s",
            registered_user.get("employee_id")
        )

        return JSONResponse(

            content={

                "status": "success",

                "message": "Identity registered successfully",

                "user": registered_user
            }
        )

    except ValueError as e:

        logger.exception("Identity registration validation failed")

        return JSONResponse(

            status_code=400,

            content={

                "status": "error",

                "message": str(e)
            }
        )

    except Exception as e:

        logger.exception("Identity registration failed")

        return JSONResponse(

            status_code=500,

            content={

                "status": "error",

                "message": str(e)
            }
        )

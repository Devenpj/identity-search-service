"""FastAPI routes for identity search, verification, admin, and OSINT APIs.

The Streamlit dashboard calls these routes. Each route validates request input,
delegates the real work to a service class, and returns JSON shaped for the UI.
Longer operations such as OSINT submission are pushed into FastAPI background
tasks while the final OSINT payload returns through the webhook endpoint.
"""

import hmac
import json
import re

import requests
from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi import Form
from fastapi import Header
from fastapi import UploadFile
from fastapi import File
from fastapi import Query
from fastapi import Request
from fastapi.responses import JSONResponse

try:
    from ..config import settings
    from ..services.database_service import DatabaseService
    from ..services.decision_service import DecisionService
    from ..services.document_verification_service import DocumentVerificationService
    from ..services.file_service import FileService
    from ..services.face_service import FaceVerificationService
    from ..services.ocr_service import OCRService
    from ..services.osint_service import OSINTService
    from ..services.risk_service import RiskScoringService
except ImportError:
    from config import settings
    from services.database_service import DatabaseService
    from services.decision_service import DecisionService
    from services.document_verification_service import DocumentVerificationService
    from services.file_service import FileService
    from services.face_service import FaceVerificationService
    from services.ocr_service import OCRService
    from services.osint_service import OSINTService
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

"""Helper functions for validating and normalizing identity search criteria and OSINT targets."""

def osint_targets_from_criteria(criteria):
    """Extract OSINT-safe structured targets from advanced search criteria."""

    allowed_fields = {
        "full_name",
        "email",
        "phone",
        "phone_number"
    }
    targets = []

    for item in criteria or []:

        field = str(item.get("field") or "").strip()
        value = str(item.get("value") or "").strip()

        normalized_field = "phone_number" if field == "phone" else field
        target = {
            "key": normalized_field,
            "value": value
        }

        if field in allowed_fields and value and target not in targets:

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


def normalize_osint_items(items):
    """Validate approved OSINT items and return provider key/value targets."""

    allowed_fields = {
        "full_name",
        "username",
        "email",
        "phone",
        "phone_number"
    }
    targets = []

    for item in items or []:

        if isinstance(item, str):

            field = "username"
            value = item.strip()

        else:

            field = str(item.get("field") or "").strip()
            value = str(item.get("value") or "").strip()

        if field not in allowed_fields:

            raise ValueError(f"Unsupported OSINT field: {field or '-'}")

        validate_identity_search_value(
            field,
            value
        )

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


@app.get("/health/full")
def health_full(

    check_osint_network: bool = Query(False)

):
    """Return API, DB, and OSINT health in one response."""

    db_payload, db_status_code = database_health_payload()
    osint_payload, osint_status_code = osint_health_payload(
        check_network=check_osint_network
    )
    status_code = 200

    if db_status_code >= 400 or osint_status_code >= 400:
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

    targets_json: str = Form(...)

):
    """Create an OSINT job only after the dashboard user approves targets."""

    try:

        if not osint_service.is_configured():

            raise ValueError(osint_service.configuration_message())

        items = json.loads(targets_json)

        if not isinstance(items, list):

            raise ValueError("OSINT targets must be a list")

        osint_targets = normalize_osint_items(items)
        logger.info(
            "Approved OSINT job creation requested: total_targets=%s",
            len(osint_targets)
        )
        osint_job = database_service.create_osint_job(
            targets=osint_targets
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

        job = request_database_service.get_osint_job(job_id)

        if not job:

            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"OSINT job not found: {job_id}"
                }
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


@app.get("/api/v1/news/clusters/top")
async def get_top_news_clusters(

    limit: int = Query(10, ge=1, le=50)

):
    """Return the top news clusters for the dashboard overview."""

    try:

        clusters = database_service.list_top_news_clusters(limit)

        return JSONResponse(
            content={
                "status": "success",
                "total_clusters": len(clusters),
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

        clusters = database_service.search_news(
            q,
            limit
        )

        return JSONResponse(
            content={
                "status": "success",
                "query": q,
                "total_clusters": len(clusters),
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

        topics = database_service.list_common_news_topics(limit)

        return JSONResponse(
            content={
                "status": "success",
                "total_topics": len(topics),
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

    cluster_id: int

):
    """Return one news cluster with sources, entities, and linked articles."""

    try:

        cluster = database_service.get_news_cluster_detail(cluster_id)

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

    request: Request,

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

        payload = await request.json()
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

        logger.info(
            "Face search database candidates loaded: total_candidates=%s",
            len(database_people)
        )

        face_search_result = face_service.find_best_database_match(
            saved_file_path,
            database_people
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

# Identity Search Service - Technical Interview Questions And Answers

## Project Overview

### 1. What problem does this project solve?

This project verifies and investigates identities using multiple signals: government ID OCR, database matching, face verification, OSINT results, and news intelligence. It helps reduce manual identity checks by combining document validation, face search, public-source intelligence, and dashboard-based review in one workflow.

### 2. What are the main modules in this project?

The main modules are:

- FastAPI backend for APIs and webhook handling.
- Streamlit dashboard for the operator UI.
- PostgreSQL for identity records, jobs, OSINT results, news data, and face embeddings.
- OCR service for document text extraction.
- Face service and separate InsightFace engine for image/video face verification.
- OSINT service for external intelligence scan integration.
- News intelligence service for external scraped news data.

### 3. Why did you use FastAPI?

FastAPI is lightweight, fast, and has built-in Swagger documentation. It supports async endpoints, file uploads, background tasks, request validation, and clean JSON APIs, which are useful for document validation, OSINT webhooks, and dashboard polling.

### 4. Why did you use Streamlit?

Streamlit allows fast dashboard development in Python. It is useful for internal tools where operators need forms, file uploads, tables, progress bars, and result visualization without building a full frontend framework.

### 5. Why PostgreSQL?

PostgreSQL provides reliable relational storage, JSONB columns for flexible OSINT/news payloads, indexing, transactions, and strong query support. It is suitable for structured identity records and semi-structured intelligence results.

## Identity Search

### 6. Explain the identity search flow.

The user selects one or more fields in the dashboard, such as full name, email, phone number, username, or document number. The frontend validates the input and sends criteria to FastAPI. The backend calls `database_service.search_identity` or the advanced search method. PostgreSQL searches matching records, and the dashboard displays the matching identities with the field that caused the match.

### 7. Should all fields match or any field match?

The system supports returning a record if any provided searchable field matches. This is useful for investigation because a user may only know one reliable identifier, such as email or phone number. The result also explains which field matched.

### 8. Why did you add input validation?

Validation prevents bad searches and bad OSINT submissions. For example, full name should not contain numbers, phone number should be 10 digits, and email should follow a strict format. This reduces false matches and unnecessary external scans.

### 9. How is username handled?

Username can be searched in the database if supported and can also be sent to the OSINT engine. It supports symbols like `@`, `_`, `.`, and `#` because social handles often contain those characters.

### 10. Why did you move identity logic into `identity_repository.py`?

The original `database_service.py` became too large. Moving identity-related database methods into `identity_repository.py` improves readability, separation of concerns, and maintainability while keeping `DatabaseService` as the main class used by routes.

## Document Verification

### 11. Explain document verification flow.

The user selects a document type and uploads an image. The backend saves the file, runs OCR/classification, validates whether the uploaded document matches the selected dropdown type, extracts identity fields, searches the database, compares face if available, calculates risk, and returns a decision: approved, rejected, or manual review.

### 12. How do you detect wrong document upload?

The OCR/document classifier tries to infer the uploaded document type. If the user selected Aadhaar but uploaded PAN, the system stops early and returns a wrong-document error instead of continuing verification.

### 13. What happens if OCR misses a document number?

The user can enter a manual document number override. The backend combines OCR output and manual values before database verification. This helps when OCR confidence is low or the image quality is poor.

### 14. What OCR-related libraries or models are used?

The project uses a specialized Indian ID validator folder with OCR/model logic for document extraction. It also uses image preprocessing and OCR parsing to extract fields like Aadhaar, PAN, voter ID, driving licence, passport, name, and DOB.

### 15. Why keep the specialized OCR model instead of replacing it?

The specialized model is tuned for Indian ID documents and gives better accuracy for Aadhaar/PAN-style layouts. Replacing it with a simple generic OCR flow could reduce accuracy.

### 16. What is the role of `risk_service.py`?

`risk_service.py` calculates the risk score based on checks like document number match, DOB match, name match, face match, and document format. It converts multiple verification signals into one decision score.

### 17. What is manual review?

Manual review is triggered when automated checks are not strong enough to approve or reject confidently. The reviewer can inspect the database record, approve the case, or update selected fields.

### 18. Why use progress bars for document validation?

Document validation can take time because it includes OCR, database search, and face comparison. Progress bars show the operator that work is continuing and prevent confusion during long-running steps.

## Face Verification

### 19. Explain face search flow.

The user uploads a face image. The backend saves it, loads database candidates, and compares the uploaded face with stored database photos. If InsightFace engine is available, embeddings are used. If unavailable, the system can fall back to OpenCV-based comparison.

### 20. Why did you separate InsightFace into `face_engine`?

InsightFace may require different dependency versions than the Indian ID validator. Keeping it in a separate service/folder avoids version conflicts and lets the main backend continue working independently.

### 21. What are face embeddings?

Face embeddings are numeric vectors that represent facial features. Similar faces should have embeddings close to each other. Storing embeddings makes future searches much faster because the system does not need to recompute every database face each time.

### 22. Why store embeddings permanently?

Permanent embeddings reduce search time. Instead of loading every image and extracting features on every search, the system can compare the uploaded embedding against stored embeddings directly.

### 23. How does video face search work?

The user uploads a video. The backend samples frames, sends frames to the InsightFace engine, detects faces, crops and enhances them, stores detected face images, and displays them in the dashboard. The user selects which detected faces should be sent for database verification.

### 24. Why not automatically verify every detected video face?

Videos may contain irrelevant faces, partial faces, or poor-quality detections. User approval prevents unnecessary database searches and reduces false matches.

### 25. How do you handle blurry or low-light faces?

The face engine performs alignment and mild enhancement. The goal is to keep the image natural while improving detection quality. It avoids excessive contrast or sharpening that can distort facial features.

### 26. What happens if the face engine is unavailable?

The backend logs the failure and can fall back to OpenCV comparison for image search. For advanced video/embedding operations, the dashboard should show a proper failure message instead of silently hanging.

## OSINT Integration

### 27. Explain the OSINT flow.

The user selects fields such as username, full name, phone, or email. The system validates them, shows the data that will be sent, asks for approval, creates a local OSINT job ID, stores it in PostgreSQL, sends the job to the OSINT engine, and waits for webhook results.

### 28. Why is OSINT asynchronous?

OSINT scans can take several minutes. If the frontend waits for the scan directly, the request may timeout. Asynchronous jobs allow the dashboard to continue polling status while the OSINT engine works independently.

### 29. What is the OSINT webhook endpoint?

The backend exposes a webhook endpoint where the OSINT engine posts completed results. The endpoint validates the token, stores raw results, normalizes important fields, and updates the job status.

### 30. How do you authenticate OSINT webhook requests?

The backend checks a secret token sent either in the query parameter or header. If the token does not match the `.env` value, the webhook returns unauthorized.

### 31. Why normalize OSINT results?

Raw OSINT JSON can be deeply nested and inconsistent. Normalization extracts important fields like platform, target, profile URL, avatar URL, bio, phone results, email results, and social matches into predictable tables/structures for display and future linking.

### 32. How do you display OSINT results?

The dashboard displays OSINT results in sections such as social media results, enriched matches, phone results, and email results. Profile URLs are shown as clickable links, and avatar images are displayed when available.

### 33. How do you handle OSINT timeout?

If a job remains pending or processing for too long, stale-job logic marks it as failed. This prevents jobs from staying in processing forever.

### 34. What if the OSINT webhook arrives without a job ID?

The backend tries to match the webhook to the latest active OSINT job using target values. If it cannot match, it returns an error because storing results without a job reference can cause data loss or mislinking.

## News Intelligence

### 35. Explain news intelligence flow.

The external news intelligence system scrapes articles and clusters, stores or posts the latest batch, and notifies this backend through a webhook. The backend validates the batch, stores ingestion status, and the dashboard fetches the latest clusters, summaries, sources, entities, and articles.

### 36. Why use a webhook for news updates?

Webhook is event-driven. The backend does not need to constantly poll. When new data is ready, the news engine notifies the backend, and the dashboard can refresh or fetch the latest data.

### 37. How do you avoid duplicate news ingestion?

The webhook uses a `batch_id`. If the same batch is sent again, the backend can treat it idempotently and avoid duplicate processing.

### 38. How are latest clusters displayed first?

Clusters are ordered by updated or published timestamp in descending order. The dashboard lets users select how many latest clusters to display.

### 39. How does keyword search work in news intelligence?

The dashboard search bar queries article titles, summaries, sources, entities, and cluster text. Suggested keywords can help users quickly search common topics.

### 40. What happens if the external news database is unreachable?

The health endpoint and dashboard should show that the news database is unavailable. The system can fall back to local data if available, but fresh external data cannot be fetched until the connection is restored.

## Database And Repository Design

### 41. Why split `database_service.py`?

The file had become too large and mixed many responsibilities. Splitting into repositories improves readability:

- `identity_repository.py` for identity/admin/manual review.
- `job_repository.py` for async jobs.
- `osint_repository.py` for OSINT.
- `news_repository.py` for news intelligence.
- `database_mixins.py` for shared lifecycle helpers.

### 42. Why keep `DatabaseService`?

Keeping `DatabaseService` avoids breaking the rest of the backend. Routes still use the same class, but the implementation is composed from repository mixins.

### 43. What is a mixin?

A mixin is a class that provides reusable methods to another class through inheritance. Here, `AsyncJobLifecycleMixin` provides shared job status methods to `DatabaseService`.

### 44. What is the benefit of `AsyncJobLifecycleMixin`?

It avoids duplicated code for marking jobs failed, timing out stale jobs, and updating progress across face, video, document, and OSINT workflows.

### 45. Why whitelist table names in `_JOB_TABLES`?

SQL parameters cannot safely bind table names. Since table names are inserted dynamically, the whitelist ensures only known job tables can be used.

### 46. Why use JSONB in PostgreSQL?

OSINT and news payloads can have changing structures. JSONB allows storing flexible structured data while still supporting indexing and querying when needed.

### 47. Why are runtime schema functions present?

Some functions create or add required tables/columns if missing. This helps the project run on older local databases. In production, these should be replaced with proper migrations.

### 48. Can `_ensure_document_columns()` be removed?

Only if every database already has the extended columns and migrations are guaranteed. Otherwise, removing it can break voter ID, driving licence, and passport features.

## Error Handling

### 49. What common errors can happen in this system?

Common errors include OCR failure, wrong document upload, face engine timeout, OSINT engine unreachable, webhook token mismatch, PostgreSQL connection failure, firewall/port blocking, and malformed input.

### 50. How do you debug OSINT connection timeout?

Check whether the OSINT server IP and port are reachable using `Test-NetConnection`, confirm both machines are on the same network, verify the server is running, and check firewall rules.

### 51. What does `WinError 10013` usually mean?

It often means Windows blocked the socket connection due to permissions, firewall, or port access restrictions.

### 52. What does `Connection timed out` mean?

The target IP/port did not respond within the timeout. This usually means the server is down, IP is wrong, firewall is blocking, or machines are not reachable on the network.

### 53. What does `401 Unauthorized` mean for webhook?

The webhook reached the backend, but the secret token was missing or incorrect.

### 54. What does `422 Unprocessable Entity` mean in FastAPI?

The request reached the endpoint, but the JSON body or form fields did not match the expected schema.

### 55. How do you prevent jobs from getting stuck?

The backend periodically marks stale `PENDING` or `PROCESSING` jobs as `FAILED` after a timeout window.

## Production Readiness

### 56. How would you make this backend production ready?

Use proper migrations, move secrets to a secret manager, add authentication and authorization, use Celery/Redis or a real task queue, add structured logging, monitoring, rate limits, Docker deployment, database backups, and API versioning.

### 57. Why should runtime schema changes be avoided in production?

Runtime schema changes can cause lock issues and unpredictable startup behavior. Production systems should use controlled migration tools like Alembic.

### 58. How would you scale face search?

Store embeddings permanently, use vector indexes such as pgvector or Qdrant, batch comparisons, and run InsightFace as a separate scalable service.

### 59. How would you secure webhooks?

Use secret headers, HMAC signatures, HTTPS, IP allowlisting, timestamp validation, replay protection, and request-size limits.

### 60. How would you monitor this project?

Track API latency, job status counts, failed jobs, webhook failures, database health, face engine health, OCR errors, OSINT timeout rate, and news ingestion batches.

## Tricky Scenario Questions

### 61. If OCR says Aadhaar but user selected PAN, what should happen?

The system should stop immediately and return a wrong-document error. It should not continue database verification because the selected document type and uploaded document do not match.

### 62. If face match is strong but document number does not match, should it approve?

No. A strong face match is useful, but document number mismatch is a major identity risk. The safest decision is manual review or rejection depending on risk policy.

### 63. If OSINT webhook arrives after the job is already failed, what should happen?

The backend can either reopen/update the job if the result is valid or keep failed status and store the late payload as audit data. Production systems should define a clear terminal-state policy.

### 64. If two database users have the same email, what should happen?

The dashboard should show both matching records and clearly state that the match happened on email. The operator should use additional fields to disambiguate.

### 65. If InsightFace and OpenCV disagree, which should be trusted?

InsightFace should generally be trusted more because embeddings are stronger for face recognition. OpenCV is useful as a fallback, not as the primary high-accuracy model.

### 66. If webhook token is leaked, what is the risk?

An attacker could send fake results to your backend. The fix is rotating the token, adding HMAC signatures, IP allowlisting, HTTPS, and replay protection.

### 67. If the dashboard refreshes during processing, will data disappear?

It should not disappear if jobs and results are stored in PostgreSQL. The dashboard can reload the job status by job ID.

### 68. If the external news database has duplicate articles, how do you prevent duplicates?

Use unique keys such as article URL, source ID, external article ID, or content hash. Upsert instead of blind insert.

### 69. If database is down, what fails first?

Identity search, job creation, document validation storage, OSINT result storage, and dashboard result loading fail because all depend on PostgreSQL.

### 70. If image upload works but face is not detected, what should the system show?

It should show a clear message like “No usable face detected” and avoid sending empty or invalid data to database verification.


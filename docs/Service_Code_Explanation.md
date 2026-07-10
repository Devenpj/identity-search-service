# Backend Services Code Explanation

This document explains the backend service layer in simple language so you can explain the project to a manager, interviewer, or teammate.

The project has many service files. Some files, especially `database_service.py`, are thousands of lines long, so this guide explains the code by line ranges and functions. Treat each range as: "these lines work together to perform this responsibility."

## How To Read This Document

- **File** means the Python file being explained.
- **Lines** means the approximate code location in the current project version.
- **What it does** explains the code behavior in easy language.
- **Why we use it** explains the reason this block exists.
- **Manager explanation** gives you a short sentence you can say directly.

---

# 1. `file_service.py`

## Purpose

`FileService` is responsible for safely accepting uploaded files and saving them into project folders.

## Flow

```text
User uploads image
→ FileService validates extension
→ saves file with safe unique name
→ returns file path to backend service
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1 | Module docstring | Describes that this file validates image uploads and stores them. | Helps future developers quickly understand the file purpose. |
| 3-4 | Imports | Imports `os` and `uuid`. | `os` handles paths, `uuid` creates unique filenames. |
| 7 | `class FileService` | Defines the upload handling service. | Keeps file-saving logic separate from routes and AI services. |
| 10-14 | `__init__` | Sets upload folder and creates it if missing. | Prevents crashes when uploads folder does not exist. |
| 16-39 | `save_upload` | Validates uploaded image, reads bytes, creates unique filename, saves to disk. | Used by document validation and face search. |
| 41-86 | `save_employee_photo` | Saves profile photo using employee ID in filename. | Admin/register identity needs stable profile-photo names. |
| 88-103 | `_validate_image_extension` | Allows only JPG, JPEG, PNG. | Protects OCR/face code from unsupported or risky file types. |

## Manager Explanation

`file_service.py` is the upload gatekeeper. It checks uploaded files and stores them safely so OCR and face services can process them.

---

# 2. `ocr_service.py`

## Purpose

`OCRService` extracts text and fields from government ID images using the specialized Indian ID validator model.

## Flow

```text
Document image path
→ run Indian ID validator model
→ read detected text JSON
→ normalize text
→ extract name, DOB, Aadhaar/PAN/other ID number
→ return structured fields
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1 | Module docstring | Explains OCR service role. | Shows this file is for external OCR/model integration. |
| 3-9 | Imports | Imports JSON, OS, regex, subprocess, sys, settings, logger. | Needed to run external model and parse its output. |
| 12 | `class OCRService` | Main OCR service class. | Groups all document OCR behavior in one place. |
| 15-20 | `__init__` | Resolves validator paths and stores last extracted face path. | Keeps model path configuration centralized. |
| 22-32 | `extract_text` | Runs model and returns extracted text. | Main text extraction entry point. |
| 34-76 | `classify_document` | Uses model/classifier output to identify document type. | Helps detect wrong document upload. |
| 78-177 | `extract_identity_fields` | Converts raw OCR data into structured fields like name, DOB, Aadhaar, PAN. | Backend and risk service need structured data, not raw OCR text. |
| 179-251 | `_run_validator_model` | Calls `inference.py` as subprocess and reads generated JSON. | Keeps specialized model isolated from main backend code. |
| 253-256 | `get_last_face_path` | Returns last face image extracted by OCR model. | Document verification uses this face for face matching. |
| 258-296 | `_get_model_name` | Maps selected document type to model name. | Different documents may require different model/classifier behavior. |
| 298-340 | Type normalization helpers | Normalizes labels like Aadhaar/Aadhar/PAN/Voter etc. | Prevents spelling variations from breaking logic. |
| 342-366 | JSON/stdout helpers | Parses model output and safely reads nested values. | OCR output can vary; helpers reduce crashes. |
| 368-451 | Cleaning helpers | Cleans Aadhaar, PAN, generic IDs, DOB. | OCR often contains spaces, symbols, or wrong formatting. |
| 453 onward | `_extract_dob` | Finds DOB from OCR fields/text. | DOB is used for database matching and risk scoring. |

## Manager Explanation

`ocr_service.py` converts document images into clean identity fields using YOLO/PaddleOCR based Indian ID validation logic.

---

# 3. `document_verification_service.py`

## Purpose

This service coordinates the complete government document validation workflow.

## Flow

```text
Uploaded document
→ validate selected document type
→ OCR extraction
→ field cleanup
→ database match
→ face match
→ risk scoring
→ decision
→ manual review if needed
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1-6 | Imports/docstring | Defines dependencies and purpose. | This file coordinates multiple services. |
| 8 | `class DocumentVerificationService` | Main document validation orchestrator. | Keeps full document workflow in one service. |
| 22-39 | `__init__` | Receives file, OCR, DB, face, risk, and decision services. | Dependency injection makes the workflow modular. |
| 41-64 | `verify` | Saves uploaded file then calls `verify_saved_file`. | Routes can pass uploaded files directly. |
| 66-218 | `verify_saved_file` | Main pipeline: validate type, OCR, DB lookup, face check, risk, decision, manual review. | This is the core identity verification flow. |
| 220-250 | `_validate_selected_document_type` | Compares dropdown-selected type with classifier-detected type. | Prevents Aadhaar selected but PAN/DL uploaded. |
| 252-277 | `_validate_extracted_document_type` | Rechecks document type using OCR content. | Some classifier outputs can be weak, so content-based validation helps. |
| 279-368 | `_infer_document_type_from_content` | Searches OCR text for Aadhaar/PAN/Voter/DL/Passport signals. | Adds extra protection for wrong document uploads. |
| 370-383 | `_raw_text_has_pan_number` | Detects PAN pattern in raw OCR text. | Helps catch PAN cards even when OCR fields are incomplete. |
| 385-394 | `_document_label` | Converts internal document type to user-readable label. | Used in error messages. |
| 396-412 | `_apply_manual_values` | Applies user override values if OCR misses ID number. | Allows operator correction without breaking workflow. |
| 414-443 | `_verify_face` | Compares OCR-extracted face with database photo. | Confirms the document belongs to the matched DB identity. |
| 445-479 | `_apply_ocr_correction_metadata` | Records OCR/manual correction details. | Helps explain how final fields were selected. |
| 481 onward | `_create_manual_review_case` | Creates review case for uncertain results. | Human reviewer handles medium-risk cases. |

## Manager Explanation

`document_verification_service.py` is the main document verification brain. It joins OCR, database lookup, face match, risk scoring, and manual review into one pipeline.

---

# 4. `risk_service.py`

## Purpose

`RiskScoringService` converts verification evidence into a numeric risk/automation score.

## Flow

```text
OCR fields + DB record + face result
→ score document number
→ score DOB
→ score name
→ score face
→ score document format
→ return score, risk level, flags, decision suggestion
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1-5 | Imports/docstring | Imports regex and datetime helpers. | Needed for field normalization. |
| 7 | `class RiskScoringService` | Defines scoring rules. | Keeps risk logic separate from document workflow. |
| 18-92 | `calculate` | Main score calculation from all evidence. | Produces final automation score and explanation. |
| 94-143 | `_score_document_number` | Scores Aadhaar/PAN/Voter/DL/Passport match. | Document number is the strongest identity proof. |
| 145-172 | `_score_dob` | Compares extracted DOB with DB DOB. | DOB confirms personal identity. |
| 174-220 | `_score_name` | Compares extracted name with DB name. | Handles exact/partial name matching. |
| 222-249 | `_score_face` | Converts face verification result into score. | Face match adds biometric confidence. |
| 251-299 | `_score_document_format` | Validates ID format patterns. | Prevents invalid-looking numbers from passing. |
| 301-325 | `_decision_for_score` | Maps score and flags to approve/manual/reject. | Makes automation decisions consistent. |
| 327-341 | `_risk_level` | Converts score into LOW/MEDIUM/HIGH risk. | Dashboard needs readable risk label. |
| 343-420 | Normalizers | Normalize IDs, document type, names, DOB. | Prevents formatting differences from hurting score. |

## Manager Explanation

`risk_service.py` gives the system a transparent scoring model so decisions are explainable instead of black-box.

---

# 5. `decision_service.py`

## Purpose

`DecisionService` turns risk assessment into final dashboard decision text.

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1 | Docstring | Says this service creates final decisions. | Makes purpose clear. |
| 4 | `class DecisionService` | Defines final decision builder. | Keeps final decision wording separate from scoring. |
| 7-53 | `build_decision` | Reads risk score/status and returns VERIFIED, MANUAL REVIEW, or REJECTED. | Dashboard and API need one consistent decision contract. |

## Manager Explanation

`decision_service.py` translates technical risk scores into business decisions the operator understands.

---

# 6. `face_service.py`

## Purpose

`FaceVerificationService` compares one face image against another or against all database photos.

## Flow

```text
Uploaded face
→ try InsightFace engine
→ if embeddings exist, use fast vector search
→ else call batch face engine
→ else fallback to OpenCV histogram/structure score
→ return best match and candidates
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1 | Docstring | Describes face comparison. | Explains fallback OpenCV role. |
| 3-13 | Imports | Imports hashing, paths, OpenCV, NumPy, requests, settings. | Needed for image loading, feature comparison, engine calls. |
| 18 | `class FaceVerificationService` | Main face comparison service. | Centralizes face matching logic. |
| 21-46 | `__init__` | Loads thresholds and Haar cascade. | Prepares fallback face detection and scoring. |
| 48-112 | `compare_faces` | Compares two image paths. | Used by document verification face-vs-DB check. |
| 114-236 | `find_best_database_match` | Compares uploaded face against all DB identities. | Used by direct face search and selected video faces. |
| 238-281 | `_compare_with_external_engine` | Calls isolated InsightFace `/verify`. | Uses stronger model when available. |
| 283-327 | `extract_external_embedding` | Calls InsightFace `/embedding`. | Used to build/search persistent embeddings. |
| 329-344 | `photo_fingerprint` | Computes hash of a profile photo. | Detects when stored photo changed. |
| 346-471 | `_find_best_with_persisted_embeddings` | Vector-searches PostgreSQL stored embeddings. | Fastest face search path. |
| 473-485 | `_identity_without_embedding` | Removes internal vector fields before API response. | Prevents large embeddings leaking to frontend. |
| 487-593 | `_find_best_with_external_engine` | Sends batches to InsightFace `/search`. | Used when embeddings are not fully ready. |
| 595-669 | `_merge_external_face_results` | Merges batch results into one best match. | Required because candidates are searched in chunks. |
| 671-689 | `_chunks` | Splits candidate list into batch-size groups. | Prevents timeout or huge request payload. |
| 691-704 | Engine URL helpers | Checks config and builds endpoint URLs. | Keeps external engine integration clean. |
| 706-778 | Image compare helpers | Prepares loaded images and compares one candidate. | OpenCV fallback path. |
| 780-858 | Image loading/extract face | Loads file and crops largest face with Haar cascade. | Needed when InsightFace is unavailable. |
| 860-948 | Scoring helpers | Histogram, structural, combined score. | Gives fallback similarity score. |
| 950-988 | Response helpers | Formats candidate/error/no-match responses. | Keeps API response consistent. |

## Manager Explanation

`face_service.py` is responsible for face matching. It prefers InsightFace embeddings for accuracy and speed, but keeps OpenCV fallback so the system still works if the face engine is unavailable.

---

# 7. `video_face_service.py`

## Purpose

`VideoFaceProcessingService` detects faces from uploaded videos and stores detected unique faces for reviewer-approved DB verification.

## Flow

```text
Video upload
→ open video with OpenCV
→ sample frames every configured seconds
→ send each frame to InsightFace engine
→ receive aligned/enhanced face crops
→ remove duplicates using embeddings
→ store unique faces immediately
→ dashboard shows them live
→ user selects faces for DB verification
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1-17 | Imports/logger | Imports OpenCV, NumPy, requests, settings, logger. | Needed for frame sampling, dedupe, engine calls, logs. |
| 22 | `class VideoFaceProcessingService` | Defines video face detection service. | Keeps video logic separate from normal face search. |
| 25-39 | `__init__` | Creates folders for sampled frames and detected face crops. | Saved crops must be available to dashboard. |
| 41-196 | `process_job` | Main video processing loop. | Runs the video job and stores detected faces incrementally. |
| 52-60 | Engine check | Fails clearly if face engine is not configured. | Video face detection requires InsightFace engine. |
| 62-67 | Open video | Uses `cv2.VideoCapture`. | Reads uploaded video frames. |
| 70-85 | FPS/sample setup | Calculates frame sampling interval and max samples. | Prevents long videos from processing every frame. |
| 89-102 | Mark job processing/logging | Updates DB and logs progress. | Dashboard sees job has started. |
| 104-184 | Frame loop | Samples frame, saves frame, detects faces, dedupes, inserts unique faces. | This is how faces appear live while the video continues. |
| 186-196 | Complete job | Stores final counts and marks job complete. | Dashboard knows processing finished. |
| 198-224 | `_detect_faces` | Calls face engine `/detect-faces`. | InsightFace does detection/alignment/crop creation. |
| 226-246 | `_save_frame` | Saves sampled frame as JPG. | Face engine reads frame from disk. |
| 248-273 | `_is_duplicate_face` | Compares embeddings to skip repeated same person. | Prevents duplicate cards for same face. |
| 275-297 | `_sample_frame_numbers` | Yields frame numbers to process. | Efficient frame sampling. |
| 299-314 | `_expected_sample_count` | Estimates total sampled frames. | Used for progress percentage. |
| 316-330 | `_progress_percent` | Converts processed samples into 10-95% progress. | Gives stable dashboard progress. |
| 332-345 | Engine helpers | Checks and builds face engine URL. | Keeps HTTP integration readable. |

## Manager Explanation

`video_face_service.py` processes videos in chunks, detects unique faces live, and waits for the operator to approve which faces should be checked against the database.

---

# 8. `osint_service.py`

## Purpose

`OSINTService` sends approved identity targets to the external OSINT engine and handles connection errors clearly.

## Flow

```text
Dashboard approves OSINT targets
→ backend creates JOB00001
→ OSINTService checks configuration
→ network preflight
→ POST /api/v1/scan to OSINT engine
→ mark DB job PROCESSING or FAILED
→ final result returns later by webhook
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1-19 | Imports/constants | Imports requests, retry, socket/url helpers. | Needed for robust external API calls. |
| 21 | `class OSINTService` | External OSINT API client. | Keeps external intelligence integration separate. |
| 24-57 | `__init__` | Creates retry-enabled requests session. | Handles temporary HTTP/server failures gracefully. |
| 59-66 | `is_configured` | Checks required OSINT URL/API key/callback. | Prevents submitting jobs with missing config. |
| 68-85 | `configuration_message` | Returns readable missing-config message. | Helps terminal/dashboard show exact setup issue. |
| 87-246 | `submit_scan` | Builds payload, verifies network, sends OSINT request, updates DB state. | Core OSINT submission workflow. |
| 248-308 | `_verify_engine_reachable` | Tests TCP connectivity to OSINT server. | Gives clear firewall/IP/server error before request. |
| 310-334 | `_explain_http_error` | Converts HTTP errors into readable reason. | Better debugging for 401/404/500 etc. |
| 336-391 | `_explain_request_error` | Explains timeout, connection refused, network unreachable. | Helps identify which machine/network is failing. |
| 393-418 | `_callback_url` | Builds callback URL with webhook token. | OSINT engine needs this to return result. |
| 420 onward | `_target_summary` | Logs/prints target info safely. | Helps track what data was sent without exposing too much. |

## Manager Explanation

`osint_service.py` is the connector between our system and the OSINT engine. It creates structured jobs, sends them, logs every step, and clearly reports network/API failures.

---

# 9. `osint_normalizer_service.py`

## Purpose

`OSINTNormalizerService` converts raw OSINT JSON into clean dashboard/database rows.

## Flow

```text
Raw OSINT webhook JSON
→ extract social profiles
→ extract phone/email results
→ extract enriched matches
→ decode avatar base64 if present
→ save avatar files
→ dedupe rows
→ store normalized tables
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1-18 | Imports/constants | Imports base64, json, os, regex, uuid, settings, logger. | Needed for parsing and saving images. |
| 20 | `class OSINTNormalizerService` | Main OSINT cleanup service. | Separates messy provider JSON from dashboard logic. |
| 23-42 | `__init__` | Sets folder for OSINT images. | Avatar images need stable local storage. |
| 44-103 | `normalize_and_store` | Builds profile/contact/match rows and saves them in DB. | Main normalization entry point. |
| 105-262 | `_profile_rows` | Extracts social media profile rows. | Dashboard social results need platform, target, profile URL, avatar, bio. |
| 264-312 | `_contact_rows` | Extracts phone/email rows. | Phone/email results should not appear as social profiles. |
| 314-360 | `_match_rows` | Extracts enriched profile matches. | Keeps additional OSINT matches available. |
| 362-384 | `_dedupe_rows` | Removes duplicate rows. | Prevents dashboard repeating same profile. |
| 386-403 | `_is_phone_or_email_platform` | Detects phone/email platforms. | Keeps categories clean. |
| 405-454 | `_save_first_base64_image` | Finds and saves first base64 avatar image. | Allows dashboard to display avatar images locally. |
| 456-556 | Base64 helpers | Decode and validate base64 image content. | Prevents broken/invalid images being saved. |
| 558-633 | URL helpers | Finds profile/avatar URLs in nested JSON. | Provider JSON may place URLs in different keys. |
| 635-708 | Text helpers | Converts nested data into readable text. | Dashboard should show readable text, not raw JSON. |
| 710-731 | Display/safe-name helpers | Cleans platform names and filenames. | Better UI labels and safe filesystem names. |

## Manager Explanation

`osint_normalizer_service.py` takes messy OSINT results and turns them into clean social, phone, email, avatar, and match data for the dashboard.

---

# 10. `news_database_service.py`

## Purpose

`NewsDatabaseService` connects to an optional external Docker/PostgreSQL news intelligence database.

## Flow

```text
NEWS_DATABASE_URL configured
→ connect to external PostgreSQL
→ prepare compatibility views if table names differ
→ fetch snapshot/latest data
→ dashboard displays latest news intelligence
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1-22 | Imports/docstring | Imports DB URL parser, psycopg2, settings, DatabaseService. | Needed for external PostgreSQL connection. |
| 24 | `class NewsDatabaseService(DatabaseService)` | Extends main DB service for external news DB. | Reuses existing news query methods where possible. |
| 27-42 | `__init__` | Connects using `NEWS_DATABASE_URL` instead of local identity DB. | Keeps news DB separate from identity DB. |
| 44-81 | `_prepare_compatibility_views` | Creates views if external table names differ. | Helps integrate with another system without rewriting queries. |
| 83-107 | `get_data_snapshot` | Counts clusters/articles and latest timestamps. | Used by health/sync status to know if new data exists. |
| 109-113 | `is_configured` | Checks if external DB URL exists. | App can fall back to local DB if not configured. |
| 115 onward | `normalized_dsn` | Returns safe DSN string. | Useful for logs without exposing secrets. |

## Manager Explanation

`news_database_service.py` lets our dashboard read latest news intelligence from a separate external PostgreSQL database without breaking the main identity database.

---

# 11. `database_service.py`

## Purpose

`DatabaseService` is the main PostgreSQL data access layer. It owns all SQL for identities, jobs, OSINT, news, embeddings, admin operations, and manual review.

## Important High-Level Flow

```text
Service needs data
→ DatabaseService builds SQL
→ executes query
→ formats row into dictionary
→ route returns JSON
→ dashboard displays result
```

## Line And Function Explanation

| Lines | Code Area | What it does | Why we use it |
|---|---|---|---|
| 1-13 | Imports/logger | Imports psycopg2, json, regex, threading, logger. | Required for DB access, JSON fields, safe schema setup. |
| 15 | `class DatabaseService` | Main DB service. | Centralizes SQL instead of spreading SQL across routes. |
| 21-34 | `__init__` | Opens PostgreSQL connection and ensures schema. | Every backend operation needs DB access. |
| 36-58 | `_ensure_runtime_schema` | Creates/migrates runtime tables once. | Avoids repeated migrations and keeps app startup safe. |
| 60-84 | `_ensure_news_ingestion_events_table` | Creates webhook audit table for news updates. | Tracks external news batches idempotently. |
| 86-108 | `_ensure_manual_review_table` | Creates manual review cases table. | Stores cases needing human review. |
| 110-191 | `_ensure_osint_jobs_table` | Creates/migrates OSINT jobs table with single `job_id`. | Tracks OSINT async workflow. |
| 193-221 | `_ensure_face_embeddings_table` | Creates persistent InsightFace embedding table. | Speeds up face search. |
| 223-271 | `_ensure_face_search_jobs_table` | Creates image face-search job table. | Dashboard can poll long-running face search. |
| 273-322 | `_ensure_video_face_search_tables` | Creates video job and detected-face tables. | Stores live detected video faces and selected verification results. |
| 324-376 | `_ensure_document_validation_jobs_table` | Creates document validation job table. | Dashboard can poll OCR/document workflow. |
| 378-467 | `_ensure_osint_normalized_tables` | Creates normalized OSINT profile/contact/match tables. | Makes OSINT retrieval structured and searchable. |
| 469-512 | Document column setup | Checks/adds voter/DL/passport columns. | Supports extended ID types. |
| 514-635 | Identity search methods | Searches DB by one or multiple fields. | Powers Identity Search dashboard. |
| 637-966 | Image face-search job methods | Create, process, complete, fail, poll face-search jobs. | Keeps image face search state persistent. |
| 968-1433 | Video face-search methods | Create video job, insert detected faces, mark selected faces searching, store match results, poll job. | Supports live video face detection and user-approved verification. |
| 1435-1756 | Document validation job methods | Create/poll/update document validation jobs. | Keeps OCR/document results persistent across dashboard switching. |
| 1758-2408 | OSINT job methods | Create OSINT jobs, mark submitted/failed/complete, normalize data. | Tracks async OSINT engine workflow. |
| 2410-2566 | Job row formatters | Converts SQL rows into JSON-ready dictionaries. | Prevents routes from dealing with raw SQL tuples. |
| 2568-2682 | News ingestion event methods | Save/latest news webhook events. | Tracks external news sync status. |
| 2684-3230 | News query methods | Top clusters, cluster detail, search, topics, row formatters. | Powers News Intelligence dashboard. |
| 3248-3457 | DB helpers/search normalizers | Close connection, allowed fields, match explanation helpers, normalize IDs. | Keeps searches safe and explainable. |
| 3459-3703 | Document DB verification | Builds WHERE conditions, verifies ID document, fuzzy Aadhaar fallback. | Finds database record for uploaded document. |
| 3705-3769 | Identity/document format helpers | Formats identity row and normalizes document type. | Standard API response shape. |
| 3771-3946 | Face embedding methods | Insert/delete/list embeddings and coverage. | Persistent embeddings make face search fast. |
| 3948-4178 | Identity/admin read methods | Get identities with photos, register/list/get records. | Powers admin and face matching. |
| 4184-4334 | Admin create/update/delete helpers | Admin CRUD operations and payload cleanup. | Lets operators manage identity master data. |
| 4336-4557 | Manual review methods | Create/get/list/update review cases. | Supports human decision flow. |
| 4559 onward | `_load_json` | Safely parses stored JSON/text columns. | Prevents bad stored JSON from crashing dashboard. |

## Manager Explanation

`database_service.py` is the central database layer. It creates required tables, stores job progress, saves AI results, manages identity records, and returns clean dictionaries to the API.

---

# 12. Service-To-Service Workflow Summary

## Document Verification

```text
routes.py
→ FileService saves upload
→ DocumentVerificationService starts flow
→ OCRService extracts text/face
→ DatabaseService finds matching identity
→ FaceVerificationService checks document face vs DB photo
→ RiskScoringService calculates score
→ DecisionService returns final decision
→ DatabaseService stores job/manual review
```

## Face Search

```text
routes.py
→ FileService saves face image
→ DatabaseService creates FACE job
→ FaceVerificationService searches embeddings/InsightFace/OpenCV
→ DatabaseService stores result
→ dashboard polls result
```

## Video Face Search

```text
routes.py
→ save uploaded video
→ DatabaseService creates VIDFACE job
→ VideoFaceProcessingService samples frames
→ face_engine detects, aligns, naturally enhances face crops
→ DatabaseService stores detected faces as PENDING
→ dashboard shows faces live
→ user selects faces
→ routes.py queues selected verification
→ FaceVerificationService checks selected faces against DB
→ DatabaseService stores MATCHED or NO_MATCH
```

## OSINT

```text
routes.py
→ DatabaseService creates JOB00001
→ OSINTService sends targets to OSINT engine
→ OSINT engine sends webhook result
→ routes.py stores raw result
→ OSINTNormalizerService stores clean profile/contact/match rows
→ dashboard displays OSINT intelligence
```

## News Intelligence

```text
External news engine scrapes data
→ stores data in external PostgreSQL
→ sends webhook notification
→ routes.py records ingestion event
→ NewsDatabaseService reads latest DB data
→ dashboard displays latest clusters/articles/topics
```

---

# 13. Simple Manager Explanation Of The Whole Service Layer

You can say:

> The backend is divided into services so each service has one responsibility. FileService handles uploads, OCRService extracts document data, DocumentVerificationService coordinates validation, FaceService performs face matching, VideoFaceService detects faces from videos, OSINTService communicates with the OSINT engine, OSINTNormalizerService cleans provider results, NewsDatabaseService reads news intelligence, RiskService scores verification confidence, DecisionService creates final decisions, and DatabaseService persists all jobs and results.

---

# 14. Most Important Things To Remember

- `routes.py` receives requests.
- `services/` contains business logic.
- `database_service.py` stores and retrieves everything.
- Long-running tasks use job IDs and polling.
- Face/video/OSINT/document workflows do not depend on dashboard memory; they persist state in PostgreSQL.
- Video faces are detected first, then user-selected faces are verified.
- OSINT/news integrations use webhook-style updates.
- InsightFace is isolated in `face_engine/` to avoid dependency conflicts with OCR models.
# Identity Verification Command Center

## Slide 1: Project Title

**Identity Verification Command Center**

A secure identity validation system that verifies government ID documents, extracts user details using OCR, matches credentials against a PostgreSQL database, compares face images, calculates risk score, and routes uncertain cases to manual review.

**Client message:**  
This project is not just a document upload tool. It is an end-to-end identity verification workflow with automation, risk scoring, and human review support.

---

## Slide 2: Business Problem

Organizations often need to verify whether a person exists in their internal database using documents such as:

- Aadhaar Card
- PAN Card
- Voter ID Card
- Driving Licence
- Passport
- Face image only

Manual verification is slow, inconsistent, and difficult to audit.

**Our solution:**  
Automate document extraction, database matching, face verification, and risk-based decision-making from one dashboard.

---

## Slide 3: High-Level System Flow

```text
Document / Face Upload
        |
        v
File Storage Layer
        |
        v
OCR + Face Extraction
        |
        v
Database Identity Matching
        |
        v
Face Verification Engine
        |
        v
Risk Scoring Engine
        |
        v
Verified / Not Verified / Manual Review
        |
        v
Streamlit Analyst Dashboard
```

**Client message:**  
Every uploaded document goes through a structured verification pipeline instead of relying on a single check.

---

## Slide 4: Mapping To The Reference Flowchart

Your reference flowchart shows:

```text
Data Sources -> Ingestion -> Resolution -> Master Profile -> Event Detection
-> EOI Management -> Filter -> Insights -> Dashboard -> Feedback Loop
```

In our project, the equivalent flow is:

```text
ID Documents / Face Images / Manual Entry
        |
        v
Upload + File Storage
        |
        v
OCR + Field Extraction
        |
        v
Credential + Face Resolution
        |
        v
Verified Identity Profile
        |
        v
Risk Scoring + Manual Review
        |
        v
Operator Dashboard
        |
        v
Approve / Reject Feedback Loop
```

---

## Slide 5: Data Sources Layer

Implemented data sources:

- Uploaded government ID document images
- Uploaded face-only images
- PostgreSQL identity database
- Manual identity registration form
- Stored profile photos
- OCR model output

Supported document types:

- Aadhaar
- PAN
- Voter ID
- Driving Licence
- Passport

**Client message:**  
The system supports both document-based verification and face-only lookup.

---

## Slide 6: Data Ingestion Layer

Implemented in:

- `backend/services/file_service.py`

Responsibilities:

- Accept uploaded files from the Streamlit UI
- Save document images safely
- Save employee profile photos
- Maintain reusable file paths for OCR and face verification

**Why it matters:**  
This separates upload handling from OCR, database, and face logic. That keeps the system stable and easier to test.

---

## Slide 7: OCR And Information Extraction

Implemented in:

- `backend/services/ocr_service.py`

What it does:

- Sends uploaded document image to the Indian ID Validator model
- Extracts raw text and structured fields
- Extracts document face image where available
- Normalizes values such as Aadhaar, PAN, DOB, and document numbers

Extracted fields:

- Full name
- Date of birth
- Aadhaar number
- PAN number
- Voter ID number
- Driving Licence number
- Passport number
- Raw OCR output

**Client message:**  
OCR is not just reading text. It converts document data into structured fields that can be verified automatically.

---

## Slide 8: Entity Resolution Engine

In the reference flowchart, entity resolution means matching multiple records that may refer to the same organization.

In our project, this becomes identity resolution:

- Match Aadhaar number
- Match PAN number
- Match Voter ID number
- Match Driving Licence number
- Match Passport number
- Normalize numbers before matching
- Ignore spaces and formatting differences

Implemented in:

- `backend/services/database_service.py`

**Example:**  
OCR may extract Aadhaar as `965569816934`, while database stores it as `9655 6981 6934`.  
Our matching normalizes both and compares the clean numeric value.

---

## Slide 9: Master Identity Profile

The database stores a master profile for each person.

Implemented profile fields:

- Employee ID
- Full name
- Date of birth
- Aadhaar number
- PAN number
- Voter ID number
- Driving Licence number
- Passport number
- Phone number
- Email
- Department
- State
- Profile photo path

Implemented in:

- PostgreSQL table: `demodataset`
- Service layer: `backend/services/database_service.py`

**Client message:**  
Once a match is found, the dashboard displays the full trusted identity profile from the database.

---

## Slide 10: Face Verification Engine

Implemented in:

- `backend/services/face_service.py`

What it does:

- Extracts face from uploaded document or face image
- Loads database profile photo
- Detects face region using OpenCV
- Resizes both faces to a common size
- Compares faces using histogram and structural similarity
- Returns match status, score, threshold, and image paths

Outputs:

- Face matched: yes/no
- Face score
- Uploaded face image
- Database face image
- Matching method

**Client message:**  
The operator can visually see both faces and the system confidence.

---

## Slide 11: Direct Face Search

Implemented feature:

Upload only a face image and search against all database profile photos.

Flow:

```text
Face Image Upload
        |
        v
Compare With All Database Photos
        |
        v
Find Best Match
        |
        v
Display User Details
```

Implemented endpoint:

- `POST /search-by-face`

Implemented dashboard tab:

- `Face Search`

**Client message:**  
Even without a document, the system can identify a user using only their face image.

---

## Slide 12: Risk Scoring Engine

Implemented in:

- `backend/services/risk_service.py`

The system now calculates a risk score out of 100.

Scoring model:

| Check | Points |
|---|---:|
| Document number match | 35 |
| Date of birth match | 20 |
| Name similarity | 20 |
| Face match | 20 |
| Document format valid | 5 |

Final decision:

- `85-100`: Verified / Low Risk
- `60-84`: Manual Review / Medium Risk
- Below `60`: Not Verified / High Risk

**Client message:**  
This makes the system explainable. We can show exactly why a case passed, failed, or needs manual review.

---

## Slide 13: Manual Review Queue

Implemented functionality:

If the system is unsure, it creates a manual review case.

Implemented table:

- `manual_review_cases`

Implemented endpoints:

- `GET /manual-review-cases`
- `POST /manual-review-cases/{case_id}/decision`

Dashboard features:

- View pending review cases
- See uploaded document
- See extracted face
- See database face
- See matched database profile
- See risk score and risk flags
- Add reviewer notes
- Approve or reject case

**Client message:**  
The system does not crash or blindly reject uncertain cases. It routes them to controlled human review.

---

## Slide 14: Input Filter And Noise Handling

The reference flowchart has an input filter for removing noise and ranking important events.

In our system, this is implemented as:

- OCR normalization
- Aadhaar spacing removal
- PAN and document number cleanup
- DOB format normalization
- Name similarity scoring
- Face confidence threshold
- Risk flags
- Manual override for missed document numbers

**Client message:**  
The system is designed to handle imperfect OCR and formatting differences.

---

## Slide 15: Analyst Dashboard

Implemented in:

- `frontend/dashboard.py`

Dashboard modules:

- Identity Search
- Document Validation
- Face Search
- Manual Review
- Register Identity

Dashboard displays:

- Search results
- Uploaded document preview
- Face comparison evidence
- Database identity profile
- Verification decision
- Risk score
- Risk flags
- Manual review queue

**Client message:**  
All verification workflows are available from one operator-ready interface.

---

## Slide 16: Identity Registration

Implemented feature:

Operators can register a new identity directly from the dashboard.

Fields:

- Employee ID
- Full name
- DOB
- Phone
- Email
- Department
- State
- Aadhaar
- PAN
- Voter ID
- Driving Licence
- Passport
- Profile photo

Implemented endpoint:

- `POST /register-identity`

**Client message:**  
The system is not only for verification. It can also expand the trusted database.

---

## Slide 17: Backend Architecture

Main backend file:

- `backend/app.py`

Service modules:

- `database_service.py`: PostgreSQL queries, search, verification, registration, review queue
- `file_service.py`: upload and photo storage
- `ocr_service.py`: OCR model integration and field extraction
- `face_service.py`: face comparison and face search
- `decision_service.py`: final verification decision
- `risk_service.py`: risk score, reasons, and flags

**Client message:**  
The backend is modular. Each service has one responsibility, which makes the project easier to maintain and extend.

---

## Slide 18: API Endpoints Implemented

Implemented APIs:

- `GET /`
- `POST /search-identity`
- `POST /validate-id`
- `POST /search-by-face`
- `POST /register-identity`
- `GET /manual-review-cases`
- `POST /manual-review-cases/{case_id}/decision`

**Client message:**  
The system is API-driven, so future integrations with other dashboards, mobile apps, or enterprise systems are possible.

---

## Slide 19: Technology Stack

Frontend:

- Streamlit

Backend:

- FastAPI
- Python

Database:

- PostgreSQL
- psycopg2

OCR:

- Indian ID Validator model
- External model integration through Python subprocess

Face Verification:

- OpenCV
- NumPy

Other:

- Requests
- Python Multipart

**Client message:**  
The stack uses proven Python tools and keeps the prototype lightweight but extensible.

---

## Slide 20: Automation Achieved Till Now

Automated steps:

- Upload document
- Extract document fields
- Extract face from document
- Normalize ID numbers
- Search database
- Compare faces
- Calculate risk score
- Decide verification status
- Create manual review case if needed
- Display database profile
- Register new identity
- Search by face only

**Client message:**  
Most of the identity verification lifecycle is now automated.

---

## Slide 21: Feedback Loop

Reference flowchart has:

- Correct Match
- Wrong Match
- False Alert
- Improve AI Models

Our implemented feedback loop:

- Manual Review tab
- Reviewer notes
- Approve case
- Reject case
- Store decision status
- Preserve review history

Future enhancement:

- Use reviewed cases to tune thresholds
- Improve risk scoring weights
- Improve OCR model accuracy
- Improve face verification confidence

---

## Slide 22: Client Demo Script

Suggested demo flow:

1. Open the Streamlit dashboard.
2. Show the five modules at the top.
3. Search for an existing identity.
4. Upload Aadhaar/PAN document.
5. Show OCR extraction and matched database profile.
6. Show uploaded face vs database face.
7. Show risk score and decision.
8. Upload a weak or mismatched case.
9. Show manual review case creation.
10. Open Manual Review tab.
11. Approve or reject with notes.
12. Register a new identity.
13. Run face-only search.

**Client message:**  
This proves the system supports both automation and controlled human decision-making.

---

## Slide 23: Key Innovation

The strongest innovation is:

**Risk-Based Identity Verification With Human-In-The-Loop Review**

Why it is powerful:

- It does not depend on only OCR
- It does not depend on only face match
- It combines multiple signals
- It explains every decision
- It avoids crashes by routing uncertain cases to review
- It supports operator approval or rejection

---

## Slide 24: Final Client Summary

We have implemented a complete identity verification command center that can:

- Validate multiple Indian government documents
- Extract identity information using OCR
- Match records in PostgreSQL
- Compare document face with database photo
- Search users using only a face image
- Register new identities
- Calculate risk score
- Create manual review cases
- Let operators approve or reject cases

**Closing line:**  
This project demonstrates a practical, automated, and explainable identity verification workflow suitable for real-world enterprise verification use cases.


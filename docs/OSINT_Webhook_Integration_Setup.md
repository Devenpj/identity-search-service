# OSINT Webhook Integration Setup

The identity search keeps returning PostgreSQL matches immediately. When the
search includes Full Name, Email, or Phone Number and OSINT is configured, the
backend also creates an OSINT job and submits it to the external provider after
the search response has been returned.

## Configure

Create a `.env` file in the project root using `.env.example`:

```env
OSINT_API_BASE_URL=https://your-osint-server.example.com
OSINT_API_KEY=replace-with-provider-api-key
OSINT_SCAN_PATH=/api/v1/scan
OSINT_CALLBACK_URL=https://your-public-backend.example.com/api/webhooks/osint-results
OSINT_WEBHOOK_TOKEN=replace-with-random-webhook-token
OSINT_REQUEST_TIMEOUT_SECONDS=20
```

`OSINT_CALLBACK_URL` must be publicly reachable by the external OSINT server.
The configured webhook token is appended to the callback URL and validated by
the backend before results are stored.

## Runtime Flow

1. Streamlit sends the existing advanced identity search request.
2. FastAPI creates a readable local OSINT job ID such as `JOB00001`.
3. FastAPI returns PostgreSQL matches and the local OSINT job ID immediately.
4. FastAPI submits targets and the same job ID to the external OSINT provider.
5. The provider sends the completed result to `/api/webhooks/osint-results`.
6. The backend stores the result in PostgreSQL.
7. Streamlit polls `/api/v1/osint/jobs/{job_id}` every 10 seconds.

## Job Status Values

The dashboard and backend use these structured statuses:

- `PENDING`: local job created and waiting for provider submission.
- `PROCESSING`: provider accepted the scan and is processing it.
- `COMPLETED`: webhook result was received and stored.
- `FAILED`: submission or provider delivery failed.

## Run In Foreground Terminal

Do not start the servers with hidden background processes while debugging.
Run them in normal terminals so logs are visible:

```powershell
cd C:\AIProjects\identity-search-service\backend
..\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000
```

In another terminal:

```powershell
cd C:\AIProjects\identity-search-service
.\.venv\Scripts\python.exe -m streamlit run frontend\dashboard.py --server.address 0.0.0.0 --server.port 8501
```

## Required Provider Contract

Scan request:

```http
POST /api/v1/scan
X-API-Key: <OSINT_API_KEY>
```

```json
{
  "job_id": "JOB00001",
  "targets": [
    {
      "key": "username",
      "value": "username"
    },
    {
      "key": "email",
      "value": "person@example.com"
    },
    {
      "key": "phone_number",
      "value": "9999999999"
    }
  ],
  "callback_url": "https://public-backend.example.com/api/webhooks/osint-results?webhook_token=..."
}
```

Immediate provider response:

```json
{
  "job_id": "JOB00001",
  "status": "processing"
}
```

Webhook payload:

```json
{
  "job_id": "JOB00001",
  "status": "completed",
  "results": {}
}
```

# News Intelligence Webhook Setup

## Purpose

The news engine writes each completed scraper batch to the shared external PostgreSQL database. After the database transaction commits, it sends this lightweight webhook notification to the Identity Search backend. The webhook verifies that the remote database is readable and records one idempotent local audit event.

## Endpoint

- Method: `POST`
- URL: use the `NEWS_WEBHOOK_URL` value from the backend environment configuration.
- Content type: `application/json`
- Authentication header: use `NEWS_WEBHOOK_HEADER_NAME`.
- Header value: use the `NEWS_WEBHOOK_TOKEN` value shared securely from the backend `.env` file.

The FastAPI backend must run with `--host 0.0.0.0` and port `8000` must be reachable from the news-engine computer.

## Completed Payload

```json
{
  "batch_id": "NEWS-20260702-001",
  "status": "completed",
  "completed_at": "2026-07-02T10:30:00+05:30",
  "source": "news-intelligence-engine",
  "counts": {
    "clusters": 12,
    "articles": 240,
    "cluster_entities": 90,
    "article_entities": 820
  }
}
```

## Failed Payload

```json
{
  "batch_id": "NEWS-20260702-002",
  "status": "failed",
  "completed_at": "2026-07-02T10:45:00+05:30",
  "source": "news-intelligence-engine",
  "message": "Scraper batch failed before database commit",
  "counts": {}
}
```

Only `completed` and `failed` are accepted. `batch_id` is the idempotency key: sending the same batch again updates its receipt instead of inserting a duplicate.

## Python Sender Example

```python
import os

import requests

webhook_url = os.environ["NEWS_WEBHOOK_URL"]
header_name = os.environ["NEWS_WEBHOOK_HEADER_NAME"]
webhook_token = os.environ["NEWS_WEBHOOK_TOKEN"]

response = requests.post(
    webhook_url,
    headers={
        "Content-Type": "application/json",
        header_name: webhook_token,
    },
    json={
        "batch_id": "NEWS-20260702-001",
        "status": "completed",
        "completed_at": "2026-07-02T10:30:00+05:30",
        "source": "news-intelligence-engine",
        "counts": {
            "clusters": 12,
            "articles": 240,
            "cluster_entities": 90,
            "article_entities": 820,
        },
    },
    timeout=15,
)
response.raise_for_status()
print(response.json())
```

## Responses

- `200`: notification accepted and audit record stored.
- `400`: invalid batch ID, status, timestamp, or counts.
- `401`: missing or invalid webhook secret.
- `413`: notification exceeds the configured payload limit.
- `503`: external news PostgreSQL could not be verified.
- `500`: unexpected backend or local database failure.

## Monitoring

- Health: `GET /health/news-db`
- Latest accepted batch: `GET /api/v1/news/sync-status/latest`
- Latest batch plus live remote totals: `GET /api/v1/news/sync-status/latest?include_live_snapshot=true`

Existing dashboard news endpoints continue reading the external database directly, so no current dashboard response shape is changed. New data appears on the next Streamlit rerun, page open, or user interaction after the webhook succeeds.
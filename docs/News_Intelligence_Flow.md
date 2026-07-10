# News Intelligence Flow

This document explains how the News Intelligence feature works end to end in
the Identity Search Service project.

## Purpose

The News Intelligence module shows the latest scraped news clusters, articles,
sources, and entities inside the Streamlit dashboard.

The external News Intelligence system is responsible for scraping and preparing
news data. This project is responsible for:

- receiving notification that new data is ready;
- connecting to the external/news PostgreSQL database;
- reading latest clusters, articles, sources, and entities;
- storing webhook receipt status locally;
- displaying fresh intelligence in the dashboard.

## Main Components

| Component | File | Purpose |
| --- | --- | --- |
| Dashboard UI | `frontend/dashboard.py` | Shows news search, latest clusters, keyword suggestions, cluster details, sources, entities, and articles |
| FastAPI routes | `backend/api/routes.py` | Provides news APIs and receives news webhook notifications |
| Local DB coordinator | `backend/services/database_service.py` | Composes repository logic through mixins |
| News repository | `backend/services/news_repository.py` | Reads local news records and stores news ingestion events |
| External news DB service | `backend/services/news_database_service.py` | Connects to the external Docker/PostgreSQL news database |
| Config | `backend/config.py` | Reads news DB URL and webhook token from `.env` |
| Setup documentation | `docs/News_Intelligence_Webhook_Setup.md` | Contract shared with the external news engine |

## High-Level Flow

```text
External News Intelligence Engine
        |
        | 1. Scrapes latest news/articles
        v
External News PostgreSQL Database
        |
        | 2. Engine sends webhook notification
        v
FastAPI Backend /api/webhooks/news-updated
        |
        | 3. Backend validates token and batch_id
        v
News ingestion event stored locally
        |
        | 4. Dashboard/API fetches latest news data
        v
Streamlit News Intelligence Dashboard
```

## Step-By-Step Flow

### 1. External Engine Scrapes News

The external News Intelligence system runs its own scraping pipeline. It may
collect 200 to 500 latest articles or news items, group them into clusters, and
extract entities such as people, places, organizations, events, dates, and
keywords.

The scraper stores its processed data in PostgreSQL tables such as:

- `clusters`
- `articles`
- `cluster_entities`
- `article_entities`

This project does not perform the scraping. It only consumes the prepared data.

### 2. Data Is Stored In External PostgreSQL

The external PostgreSQL database may run inside Docker or on another machine.
This backend connects to it using:

```env
NEWS_DATABASE_URL=postgresql://postgres:password@host:port/database
```

Example:

```env
NEWS_DATABASE_URL=postgresql://postgres:password@10.5.50.101:5433/osint
```

The connection is handled by:

```text
backend/services/news_database_service.py
```

### 3. External Engine Sends Webhook Notification

After scraping and storing data, the external engine sends a POST request to:

```text
POST /api/webhooks/news-updated
```

Example URL:

```text
http://10.5.50.242:8000/api/webhooks/news-updated
```

The request must include the authentication header:

```http
X-News-Webhook-Secret: YOUR_NEWS_WEBHOOK_TOKEN
```

The backend compares that header with:

```env
NEWS_WEBHOOK_TOKEN=your-secret-token
```

If the token is wrong, the backend returns `401 Unauthorized`.

### 4. Webhook Payload Is Validated

The webhook should send a JSON body with a stable batch ID.

Example:

```json
{
  "batch_id": "NEWS-20260709-101500",
  "status": "completed",
  "source": "news-intelligence-engine",
  "reported_counts": {
    "clusters": 58,
    "articles": 420,
    "cluster_entities": 1000,
    "article_entities": 2400
  },
  "engine_completed_at": "2026-07-09T10:15:00Z"
}
```

The `batch_id` is important because it makes webhook handling idempotent.
If the same batch is sent twice, the backend can identify it and avoid treating
it as a completely new event.

### 5. Backend Stores The Ingestion Event

The backend stores the webhook receipt in the local PostgreSQL table:

```text
news_ingestion_events
```

This stores:

- `batch_id`
- `status`
- source name
- reported counts
- database snapshot
- raw payload
- error message, if any
- received timestamp

This is handled by:

```text
backend/services/news_repository.py
```

The event table helps the system answer:

- Did the news engine notify us?
- Which batch was received?
- Was the batch completed or failed?
- How many clusters/articles were reported?
- When was the last update received?

### 6. Backend Reads Latest News Data

The dashboard does not directly connect to the external database.

Instead, the dashboard calls FastAPI endpoints such as:

```text
GET /api/v1/news/clusters/top
GET /api/v1/news/search
GET /api/v1/news/topics/common
GET /api/v1/news/clusters/{cluster_id}
GET /api/v1/news/sync-status/latest
GET /health/news-db
```

FastAPI uses `NewsDatabaseService` when the external DB is configured and
available.

If needed, the backend can fall back to local news data.

### 7. Dashboard Displays Latest Clusters

The News Intelligence section shows latest clusters first.

Each cluster can display:

- title
- summary
- updated date
- article count
- source count
- key entities
- source breakdown
- related articles

The operator can choose how many top clusters to see, such as:

```text
10, 20, 30, 40, or more
```

### 8. Search And Keyword Flow

The dashboard includes a search bar for searching:

- news topic
- article title
- source
- entity
- location
- person
- organization

When the user types text, relevant keyword suggestions can appear. Selecting a
keyword or searching text triggers the news search endpoint.

Search results are shown before the default top-cluster list so the operator
sees relevant results immediately.

### 9. Cluster Detail Flow

When the user opens a cluster:

1. The dashboard sends the cluster ID to the backend.
2. The backend fetches the cluster summary.
3. It also fetches related sources.
4. It fetches key entities.
5. It fetches related articles.
6. The dashboard displays everything in a readable investigation layout.

## Error Handling

### Invalid Token

Problem:

```text
401 Unauthorized
```

Reason:

The external engine sent a missing or incorrect `X-News-Webhook-Secret`.

Fix:

Make sure both systems use the same `NEWS_WEBHOOK_TOKEN`.

### Invalid Payload

Problem:

```text
422 Unprocessable Entity
```

Reason:

The JSON body does not match what the backend expects.

Fix:

Send required fields such as `batch_id` and `status`.

### News DB Unreachable

Problem:

```text
Connection timeout
```

Reasons:

- Docker PostgreSQL is not running.
- Wrong host or port.
- Firewall is blocking the port.
- Both machines are not on the same network.

Fix:

Use:

```powershell
Test-NetConnection <news-db-ip> -Port <port>
```

### Duplicate Batch

Problem:

Same webhook is sent multiple times.

Expected behavior:

The backend should use `batch_id` to update or safely reuse the existing batch
receipt instead of creating confusing duplicate status records.

## Why This Design Is Good

This design is simple and production-friendly because:

- scraping is isolated in the external news engine;
- this backend only consumes prepared intelligence;
- webhook avoids constant polling;
- PostgreSQL stores latest and old data;
- dashboard always fetches through backend APIs;
- health endpoints help debug database connectivity;
- batch IDs reduce duplicate ingestion problems.

## Current Important Files

```text
backend/api/routes.py
backend/services/news_database_service.py
backend/services/news_repository.py
backend/services/database_service.py
backend/config.py
frontend/dashboard.py
docs/News_Intelligence_Webhook_Setup.md
```

## Simple Explanation For Manager

The News Intelligence engine scrapes and stores news in its own PostgreSQL
database. Once scraping is complete, it notifies our FastAPI backend through a
secure webhook. Our backend validates the request, stores the batch receipt,
connects to the news database, and exposes clean APIs for the Streamlit
dashboard. The dashboard then shows latest clusters, summaries, sources,
entities, articles, and search results in an operator-friendly way.


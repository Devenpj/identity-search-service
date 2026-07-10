# DRISHTI Client Demo Implementation

This project demonstrates DRISHTI inside the existing Identity Search Service as a working prototype. The demo now runs DRISHTI through the existing main service path: `DrishtiService(database_service)` first reads current News Intelligence clusters/articles from `NewsRepositoryMixin`, then falls back to default DRISHTI records when the news database has no data. The same API/UI shape can later connect to official APIs, licensed feeds, crawler pools, GPU NLP models, and production storage.

## Where The Functionality Lives

| Requirement | Backend service | API | Dashboard tab | Demo content shown |
| --- | --- | --- | --- | --- |
| Data Acquisition & Resilience | Main FastAPI route -> `DrishtiService(database_service)` -> `refresh_sources`, `acquisition_status` | `GET /api/v1/drishti/overview`, `POST /api/v1/drishti/refresh` | Acquisition | Source status, 20-minute refresh, attempts, alternate crawler, unresolved CAPTCHA/source flags |
| Advanced Search & Discovery | `search`, `recommend_keywords`, `describe_query` over existing `NewsRepositoryMixin` data | `POST /api/v1/drishti/search` | Search | Boolean/phrase/wildcard search, keyword recommendations, location/language/emotion filters |
| Narrative & Sentiment Intelligence | `narrative_cards`, `_sentiment_score`, `_emotion`, `_risk_prediction` | Overview and Search APIs | Narratives | Fault lines, stance, risk score, confidence, sub-narratives, summaries |
| Visualization & Analytics | `knowledge_graph`, `heatmap` | `GET /api/v1/drishti/overview` | Visual Analytics | Source breakdown, sentiment distribution, heatmap points, graph edges |
| Infrastructure | `overview` deployment metadata | `GET /api/v1/drishti/overview` | Implementation Map | Cloud GPU ready, no OpenAI dependency, Docker/Kubernetes target |
| Content Operations | `generate_content` | `POST /api/v1/drishti/content/generate` | Content Operations | Human-reviewable candidate outputs to create/change a narrative |

## Client Demo Flow

1. Open Streamlit and choose **DRISHTI Intelligence** from the sidebar.
2. Start with **Implementation Map** to explain how each PDF requirement maps to the main service path, endpoint, UI tab, and current data source.
3. Open **Acquisition** and click **Refresh Sources** to show the 20-minute refresh model, automatic attempts, alternate crawler path, and CAPTCHA flag.
4. Open **Search** and run a query like `"public trust" OR rumour* AND NOT spam`, then filter by location, emotion, or language.
5. Open **Narratives** to show fault lines, sentiment, stance, sub-narrative summaries, risk prediction, and confidence.
6. Open **Visual Analytics** to show knowledge graph relationships and heatmap-ready location points.
7. Open **Content Operations** to generate review-required content candidates from an analyst narrative.

## Production Upgrade Path

- Keep the current `NewsRepositoryMixin` integration and add dedicated DRISHTI tables or Elasticsearch/OpenSearch indexing when ingestion volume grows.
- Replace heuristic NLP with GPU-hosted local models for NER, translation, sentiment, stance, clustering, summarization, and LLM generation.
- Add scheduled background refresh every 20 minutes using FastAPI background tasks, Celery, APScheduler, or Kubernetes CronJobs.
- Wire source connectors to official APIs, licensed aggregators, and compliant crawler adapters.
- Render map points with a map component and graph nodes with a network visualization component when the UI stack is ready for those dependencies.

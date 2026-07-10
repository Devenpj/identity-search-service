"""Local DRISHTI intelligence prototype service.

The service keeps the DRISHTI workflow usable without OpenAI or live crawler
dependencies. Real deployments can replace the sample feed and heuristic NLP
methods with official APIs, licensed aggregators, and GPU-hosted models while
preserving the API shape used by the dashboard.
"""

import math
import re
from collections import Counter
from datetime import datetime
from datetime import timedelta


class DrishtiService:
    """Provide resilient acquisition, search, analytics, and content operations."""

    REFRESH_INTERVAL_MINUTES = 20

    def __init__(self, database_service=None):
        self.database_service = database_service
        self.sources = [
            {
                "name": "News API Feed",
                "type": "official_api",
                "status": "available",
                "attempts": 1,
                "alternate": "Licensed News Aggregator",
                "last_error": ""
            },
            {
                "name": "Social Listening Feed",
                "type": "licensed_aggregator",
                "status": "available",
                "attempts": 1,
                "alternate": "Archive Batch Import",
                "last_error": ""
            },
            {
                "name": "Regional Web Monitor",
                "type": "crawler",
                "status": "captcha_unresolved",
                "attempts": 3,
                "alternate": "Crawler Pool B",
                "last_error": "Unresolved CAPTCHA after automatic reattempts"
            },
            {
                "name": "Public Forum Monitor",
                "type": "crawler",
                "status": "available",
                "attempts": 2,
                "alternate": "Proxy Route C",
                "last_error": ""
            }
        ]
        self.posts = self._build_seed_posts()
        self.last_refresh = datetime.utcnow() - timedelta(minutes=7)

    def _build_seed_posts(self):
        base = datetime.utcnow()
        return [
            {
                "id": "DRI-001",
                "source": "News API Feed",
                "author": "north_watch",
                "text": "Border logistics delays trigger anger in local markets near Srinagar.",
                "language": "en",
                "location": "Srinagar",
                "lat": 34.0837,
                "lon": 74.7973,
                "created_at": base - timedelta(hours=1),
                "narrative": "Logistics Pressure",
                "fault_line": "Security and supply confidence",
                "stance": "Neutral",
                "risk_markers": ["supply anxiety", "localized anger"]
            },
            {
                "id": "DRI-002",
                "source": "Social Listening Feed",
                "author": "civic_voice",
                "text": "Youth groups ask for transparent updates after flood relief rumours spread online.",
                "language": "en",
                "location": "Guwahati",
                "lat": 26.1445,
                "lon": 91.7362,
                "created_at": base - timedelta(hours=3),
                "narrative": "Relief Trust",
                "fault_line": "Governance credibility",
                "stance": "Neutral",
                "risk_markers": ["rumour velocity", "trust deficit"]
            },
            {
                "id": "DRI-003",
                "source": "Public Forum Monitor",
                "author": "trade_signal",
                "text": "Factory shutdown claims are exaggerated, but workers are worried about wages.",
                "language": "en",
                "location": "Pune",
                "lat": 18.5204,
                "lon": 73.8567,
                "created_at": base - timedelta(hours=5),
                "narrative": "Economic Anxiety",
                "fault_line": "Employment and livelihood",
                "stance": "Neutral",
                "risk_markers": ["labour anxiety"]
            },
            {
                "id": "DRI-004",
                "source": "Regional Web Monitor",
                "author": "regional_digest",
                "text": "स्थानीय पोस्टों में पानी की कमी और प्रशासनिक प्रतिक्रिया पर नाराजगी दिखी।",
                "language": "hi",
                "translation": "Local posts show anger about water shortage and administrative response.",
                "location": "Jaipur",
                "lat": 26.9124,
                "lon": 75.7873,
                "created_at": base - timedelta(hours=8),
                "narrative": "Public Services",
                "fault_line": "Resource access",
                "stance": "Neutral",
                "risk_markers": ["resource grievance", "administration criticism"]
            },
            {
                "id": "DRI-005",
                "source": "Social Listening Feed",
                "author": "student_forum",
                "text": "Campus protest clips are being reposted with misleading old visuals.",
                "language": "en",
                "location": "Delhi",
                "lat": 28.6139,
                "lon": 77.2090,
                "created_at": base - timedelta(hours=14),
                "narrative": "Information Integrity",
                "fault_line": "Youth mobilization",
                "stance": "Anti-Adversary",
                "risk_markers": ["old media reuse", "misleading visuals"]
            },
            {
                "id": "DRI-006",
                "source": "News API Feed",
                "author": "coastal_alert",
                "text": "Fisher groups welcome cyclone warning updates, but request multilingual alerts.",
                "language": "en",
                "location": "Chennai",
                "lat": 13.0827,
                "lon": 80.2707,
                "created_at": base - timedelta(hours=20),
                "narrative": "Disaster Preparedness",
                "fault_line": "Public safety messaging",
                "stance": "Anti-Adversary",
                "risk_markers": ["language gap"]
            }
        ]

    def refresh_sources(self):
        """Simulate the 20-minute acquisition refresh and crawler resilience state."""

        self.last_refresh = datetime.utcnow()
        for source in self.sources:
            if source["status"] == "captcha_unresolved":
                source["attempts"] = max(source["attempts"], 3)
                continue
            source["status"] = "available"
            source["attempts"] = max(source["attempts"], 1)
        return self.acquisition_status()

    def acquisition_status(self):
        next_refresh = self.last_refresh + timedelta(minutes=self.REFRESH_INTERVAL_MINUTES)
        unavailable = [
            source for source in self.sources
            if source["status"] != "available"
        ]
        return {
            "refresh_interval_minutes": self.REFRESH_INTERVAL_MINUTES,
            "last_refresh": self.last_refresh.isoformat() + "Z",
            "next_refresh": next_refresh.isoformat() + "Z",
            "sources": self.sources,
            "unavailable_sources": unavailable,
            "total_sources": len(self.sources),
            "available_sources": len(self.sources) - len(unavailable)
        }

    def overview(self):
        posts = self._enriched_posts(self._load_posts())
        sentiment_counts = Counter(post["sentiment"] for post in posts)
        source_counts = Counter(post["source"] for post in posts)
        location_counts = Counter(post["location"] for post in posts)
        narrative_counts = Counter(post["narrative"] for post in posts)
        return {
            "acquisition": self.acquisition_status(),
            "data_source": self.last_data_source,
            "metrics": {
                "posts_analyzed": len(posts),
                "alerts_triggered": sum(1 for post in posts if post["risk_score"] >= 0.65),
                "negative": sentiment_counts.get("Negative", 0),
                "neutral": sentiment_counts.get("Neutral", 0),
                "positive": sentiment_counts.get("Positive", 0),
                "languages": len(set(post["language"] for post in posts))
            },
            "source_breakdown": dict(source_counts),
            "sentiment_distribution": dict(sentiment_counts),
            "location_breakdown": dict(location_counts),
            "trending_keywords": self.recommend_keywords(posts),
            "emerging_topics": [
                {"topic": topic, "mentions": count}
                for topic, count in narrative_counts.most_common()
            ],
            "narratives": self.narrative_cards(posts),
            "knowledge_graph": self.knowledge_graph(posts),
            "heatmap": self.heatmap(posts),
            "deployment": {
                "cloud_gpu_ready": True,
                "openai_dependency": False,
                "model_runtime": "Pluggable local/GPU LLM endpoint",
                "container_target": "Docker/Kubernetes"
            }
        }

    def search(self, query="", locations=None, emotions=None, languages=None):
        locations = set(locations or [])
        emotions = set(emotions or [])
        languages = set(languages or [])
        posts = self._enriched_posts(self._load_posts())
        filtered = []
        for post in posts:
            if locations and post["location"] not in locations:
                continue
            if emotions and post["emotion"] not in emotions:
                continue
            if languages and post["language"] not in languages:
                continue
            if query and not self._matches_query(post, query):
                continue
            filtered.append(post)

        return {
            "query": query,
            "data_source": self.last_data_source,
            "parsed_query": self.describe_query(query),
            "total": len(filtered),
            "results": filtered,
            "keyword_recommendations": self.recommend_keywords(filtered or posts),
            "narratives": self.narrative_cards(filtered or posts),
            "knowledge_graph": self.knowledge_graph(filtered or posts),
            "heatmap": self.heatmap(filtered or posts)
        }

    def generate_content(self, narrative, content_type="Short Post", language="English", tone="Calm", include_image=False):
        narrative = (narrative or "public trust and information integrity").strip()
        content_type = content_type or "Short Post"
        language = language or "English"
        tone = tone or "Calm"
        base = (
            f"{tone} {content_type.lower()} in {language}: "
            f"Address the narrative around {narrative}. Use verified facts, acknowledge public concerns, "
            "avoid inflammatory claims, and guide audiences toward official updates."
        )
        outputs = [
            {
                "model": "local-llm-primary",
                "content": base,
                "confidence": 0.78
            },
            {
                "model": "local-llm-review",
                "content": (
                    f"{content_type} draft: Communities discussing {narrative} need timely, multilingual, "
                    "source-linked updates. Share what is known, what is being verified, and how people can report issues."
                ),
                "confidence": 0.72
            }
        ]
        return {
            "narrative": narrative,
            "content_type": content_type,
            "language": language,
            "tone": tone,
            "include_image": bool(include_image),
            "review_required": True,
            "outputs": outputs,
            "image_prompt": (
                f"Documentary-style public information visual about {narrative}, "
                "clear civic communication, no logos"
            ) if include_image else ""
        }

    def _load_posts(self):
        """Load DRISHTI records from existing services, falling back to demo data."""

        news_posts = self._load_news_posts_from_database()
        if news_posts:
            self.last_data_source = "existing_news_intelligence_service"
            return news_posts

        self.last_data_source = "default_demo_data"
        return self.posts

    def _load_news_posts_from_database(self):
        """Convert existing News Intelligence clusters/articles into DRISHTI posts."""

        if not self.database_service:
            return []

        try:
            clusters = self.database_service.list_top_news_clusters(limit=25)
        except Exception:
            return []

        posts = []
        for cluster in clusters or []:
            cluster_id = cluster.get("cluster_id")
            detail = None
            if cluster_id:
                try:
                    detail = self.database_service.get_news_cluster_detail(cluster_id)
                except Exception:
                    detail = None
            detail = detail or cluster
            articles = detail.get("articles") or []
            entities = detail.get("entities") or cluster.get("entities") or []
            sources = detail.get("sources") or []
            source_name = (
                cluster.get("top_source")
                or (sources[0].get("source") if sources else None)
                or "News Intelligence"
            )
            location = self._infer_location_from_news(detail, articles, entities)
            lat, lon = self._location_coordinates(location)
            updated_at = self._parse_datetime(cluster.get("updated_at")) or datetime.utcnow()
            risk_markers = [
                str(entity.get("entity_name"))
                for entity in entities[:4]
                if entity.get("entity_name")
            ]

            if articles:
                for index, article in enumerate(articles[:3], start=1):
                    published_at = (
                        self._parse_datetime(article.get("published_at"))
                        or self._parse_datetime(article.get("created_at"))
                        or updated_at
                    )
                    posts.append({
                        "id": f"NEWS-{cluster_id}-{index}",
                        "source": article.get("source") or source_name,
                        "author": article.get("source") or source_name,
                        "text": " ".join(
                            value for value in [
                                article.get("title"),
                                article.get("content"),
                                cluster.get("cluster_summary")
                            ]
                            if value
                        ),
                        "language": self._detect_language(article.get("content") or article.get("title") or ""),
                        "location": location,
                        "lat": lat,
                        "lon": lon,
                        "created_at": published_at,
                        "narrative": cluster.get("cluster_name") or f"News Cluster {cluster_id}",
                        "fault_line": self._infer_fault_line(cluster, entities),
                        "stance": self._infer_stance(cluster, articles),
                        "risk_markers": risk_markers or ["news velocity"]
                    })
            else:
                posts.append({
                    "id": f"NEWS-{cluster_id}",
                    "source": source_name,
                    "author": source_name,
                    "text": " ".join(
                        value for value in [
                            cluster.get("cluster_name"),
                            cluster.get("cluster_summary")
                        ]
                        if value
                    ),
                    "language": self._detect_language(cluster.get("cluster_summary") or ""),
                    "location": location,
                    "lat": lat,
                    "lon": lon,
                    "created_at": updated_at,
                    "narrative": cluster.get("cluster_name") or f"News Cluster {cluster_id}",
                    "fault_line": self._infer_fault_line(cluster, entities),
                    "stance": self._infer_stance(cluster, []),
                    "risk_markers": risk_markers or ["news cluster"]
                })

        return posts

    def _parse_datetime(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _detect_language(self, text):
        if re.search(r"[\u0900-\u097F]", text or ""):
            return "hi"
        return "en"

    def _infer_location_from_news(self, cluster, articles, entities):
        known_locations = [
            "Srinagar", "Guwahati", "Pune", "Jaipur", "Delhi", "Chennai",
            "Mumbai", "Bengaluru", "Kolkata", "Hyderabad", "Mathura", "Lucknow"
        ]
        haystack = " ".join(
            str(value or "")
            for value in [
                cluster.get("cluster_name"),
                cluster.get("cluster_summary"),
                " ".join(article.get("title") or "" for article in articles or []),
                " ".join(entity.get("entity_name") or "" for entity in entities or [])
            ]
        ).lower()
        for location in known_locations:
            if location.lower() in haystack:
                return location
        for entity in entities or []:
            if str(entity.get("entity_type") or "").lower() in {"location", "place", "geo", "city"}:
                return str(entity.get("entity_name") or "India")
        return "India"

    def _location_coordinates(self, location):
        coordinates = {
            "India": (22.9734, 78.6569),
            "Srinagar": (34.0837, 74.7973),
            "Guwahati": (26.1445, 91.7362),
            "Pune": (18.5204, 73.8567),
            "Jaipur": (26.9124, 75.7873),
            "Delhi": (28.6139, 77.2090),
            "Chennai": (13.0827, 80.2707),
            "Mumbai": (19.0760, 72.8777),
            "Bengaluru": (12.9716, 77.5946),
            "Kolkata": (22.5726, 88.3639),
            "Hyderabad": (17.3850, 78.4867),
            "Mathura": (27.4924, 77.6737),
            "Lucknow": (26.8467, 80.9462)
        }
        return coordinates.get(location, coordinates["India"])

    def _infer_fault_line(self, cluster, entities):
        text = " ".join([
            str(cluster.get("cluster_name") or ""),
            str(cluster.get("cluster_summary") or ""),
            " ".join(str(entity.get("entity_name") or "") for entity in entities or [])
        ]).lower()
        if any(word in text for word in ("security", "border", "attack", "protest")):
            return "Security and public order"
        if any(word in text for word in ("relief", "flood", "cyclone", "health", "water")):
            return "Public services and safety"
        if any(word in text for word in ("job", "factory", "wage", "price", "trade")):
            return "Economic and livelihood confidence"
        if any(word in text for word in ("misleading", "rumour", "fake", "viral")):
            return "Information integrity"
        return "Emerging public narrative"

    def _infer_stance(self, cluster, articles):
        text = " ".join([
            str(cluster.get("cluster_name") or ""),
            str(cluster.get("cluster_summary") or ""),
            " ".join(str(article.get("title") or "") for article in articles or [])
        ]).lower()
        if any(word in text for word in ("misleading", "fake", "verified", "clarification", "debunk")):
            return "Anti-Adversary"
        return "Neutral"
    def _enriched_posts(self, posts):
        return [self._enrich_post(post) for post in posts]

    def _enrich_post(self, post):
        text = self._search_text(post)
        sentiment_score = self._sentiment_score(text)
        sentiment = "Positive" if sentiment_score > 0.2 else "Negative" if sentiment_score < -0.2 else "Neutral"
        emotion = self._emotion(text)
        risk_score = self._risk_score(post, sentiment, emotion)
        enriched = dict(post)
        enriched.update({
            "created_at": post["created_at"].isoformat() + "Z",
            "translated_text": post.get("translation") or post["text"],
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "emotion": emotion,
            "risk_score": risk_score,
            "risk_prediction": self._risk_prediction(risk_score),
            "target_audience": self._target_audience(post),
            "confidence": round(0.62 + min(0.34, risk_score / 3), 2)
        })
        return enriched

    def _search_text(self, post):
        return " ".join([
            post.get("text", ""),
            post.get("translation", ""),
            post.get("author", ""),
            post.get("location", ""),
            post.get("narrative", ""),
            post.get("fault_line", "")
        ]).lower()

    def _matches_query(self, post, query):
        text = self._search_text(post)
        expression = query.strip()
        expression = re.sub(r"\bNOT\s+(@?[\w*.-]+)", r"-\1", expression, flags=re.IGNORECASE)
        if not expression:
            return True

        phrases = re.findall(r'"([^"]+)"', expression)
        for phrase in phrases:
            if phrase.lower() not in text:
                return False
            expression = expression.replace(f'"{phrase}"', " ")

        or_groups = re.split(r"\s+OR\s+", expression, flags=re.IGNORECASE)
        group_matches = []
        for group in or_groups:
            terms = re.split(r"\s+AND\s+|\s+", group, flags=re.IGNORECASE)
            required = []
            blocked = []
            for term in terms:
                term = term.strip()
                if not term:
                    continue
                if term.upper() == "NOT":
                    continue
                if term.upper().startswith("NOT "):
                    blocked.append(term[4:].strip())
                elif term.startswith("-"):
                    blocked.append(term[1:])
                else:
                    required.append(term)
            has_required = all(self._term_matches(text, term) for term in required)
            has_blocked = any(self._term_matches(text, term) for term in blocked)
            group_matches.append(has_required and not has_blocked)
        return any(group_matches) if group_matches else True

    def _term_matches(self, text, term):
        normalized = term.lower().lstrip("@")
        if not normalized:
            return True
        pattern = re.escape(normalized).replace("\\*", ".*")
        return re.search(pattern, text) is not None

    def describe_query(self, query):
        return {
            "supports": ["phrase search", "AND", "OR", "NOT/-", "wildcard *", "mentions @"],
            "phrases": re.findall(r'"([^"]+)"', query or ""),
            "raw": query or ""
        }

    def recommend_keywords(self, posts):
        stopwords = {
            "about", "after", "being", "with", "from", "local", "posts", "updates",
            "online", "near", "are", "the", "and", "for", "but", "old"
        }
        words = []
        for post in posts:
            words.extend(
                word for word in re.findall(r"[A-Za-z][A-Za-z-]{3,}", self._search_text(post))
                if word not in stopwords
            )
        return [
            {"keyword": keyword, "score": count}
            for keyword, count in Counter(words).most_common(12)
        ]

    def narrative_cards(self, posts):
        grouped = {}
        for post in posts:
            grouped.setdefault(post["narrative"], []).append(post)

        cards = []
        for narrative, rows in grouped.items():
            risks = Counter(marker for row in rows for marker in row.get("risk_markers", []))
            sentiments = Counter(row.get("sentiment") for row in rows)
            avg_risk = sum(row.get("risk_score", 0) for row in rows) / max(1, len(rows))
            cards.append({
                "narrative": narrative,
                "summary": self._summarize(rows),
                "sub_narratives": [marker for marker, _ in risks.most_common(4)],
                "fault_line": rows[0].get("fault_line"),
                "stance": rows[0].get("stance"),
                "sentiment_breakdown": dict(sentiments),
                "target_audience": self._target_audience(rows[0]),
                "risk_score": round(avg_risk, 2),
                "risk_prediction": self._risk_prediction(avg_risk),
                "confidence": round(0.68 + min(0.27, len(rows) / 20), 2)
            })
        return sorted(cards, key=lambda card: card["risk_score"], reverse=True)

    def knowledge_graph(self, posts):
        nodes = {}
        edges = []
        for post in posts:
            for key, node_type in (
                (post["author"], "actor"),
                (post["narrative"], "narrative"),
                (post["location"], "location"),
                (post["source"], "source")
            ):
                nodes[key] = {"id": key, "label": key, "type": node_type}
            edges.extend([
                {"source": post["author"], "target": post["narrative"], "relation": "amplifies"},
                {"source": post["narrative"], "target": post["location"], "relation": "observed_in"},
                {"source": post["source"], "target": post["narrative"], "relation": "reported"}
            ])
        return {"nodes": list(nodes.values()), "edges": edges}

    def heatmap(self, posts):
        return [
            {
                "location": post["location"],
                "lat": post["lat"],
                "lon": post["lon"],
                "volume": 1,
                "sentiment": post.get("sentiment", "Neutral"),
                "risk_score": post.get("risk_score", 0)
            }
            for post in posts
        ]

    def _sentiment_score(self, text):
        positive = {"welcome", "transparent", "verified", "preparedness", "official"}
        negative = {"anger", "worried", "rumours", "misleading", "shortage", "delays", "anxiety"}
        score = sum(1 for word in positive if word in text) - sum(1 for word in negative if word in text)
        return round(max(-1, min(1, score / 3)), 2)

    def _emotion(self, text):
        if any(word in text for word in ("anger", "नाराजगी", "shortage")):
            return "Anger"
        if any(word in text for word in ("worried", "anxiety", "rumours")):
            return "Fear"
        if any(word in text for word in ("welcome", "transparent")):
            return "Trust"
        return "Neutral"

    def _risk_score(self, post, sentiment, emotion):
        base = 0.25 + 0.1 * len(post.get("risk_markers", []))
        if sentiment == "Negative":
            base += 0.2
        if emotion in {"Anger", "Fear"}:
            base += 0.18
        if post.get("language") != "en":
            base += 0.07
        return round(min(0.95, base), 2)

    def _risk_prediction(self, risk_score):
        if risk_score >= 0.7:
            return "Escalating narrative likely without rapid clarification"
        if risk_score >= 0.5:
            return "Monitor for volume spikes and cross-location replication"
        return "Stable with routine monitoring"

    def _target_audience(self, post):
        location = post.get("location", "regional")
        language = "Hindi" if post.get("language") == "hi" else "English"
        return f"{location} local audience, {language} language segment"

    def _summarize(self, rows):
        first = rows[0]
        return (
            f"{first['narrative']} is appearing around {first['location']} with "
            f"{len(rows)} linked item(s), focused on {first['fault_line'].lower()}."
        )

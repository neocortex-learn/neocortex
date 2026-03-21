"""Recommendation tracking — matches reads to recommendations and updates gap status."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from neocortex.models import RecommendationRecord


def match_recommendation(
    source: str,
    title: str,
    pending: list[RecommendationRecord],
) -> RecommendationRecord | None:
    """Match a read source/title against pending recommendations. Three-tier matching."""
    if not pending:
        return None

    normalized_source = _normalize_url(source)
    for rec in pending:
        for res in rec.resources:
            if res.url and _normalize_url(res.url) == normalized_source:
                return rec

    if source.startswith(("http://", "https://")):
        source_domain = urlparse(source).netloc.lower()
        source_path = urlparse(source).path.lower()
        for rec in pending:
            for res in rec.resources:
                if not res.url:
                    continue
                res_domain = urlparse(res.url).netloc.lower()
                if source_domain != res_domain:
                    continue
                keywords = _extract_keywords(rec.topic)
                if any(kw in title.lower() or kw in source_path for kw in keywords):
                    return rec

    return None


def _normalize_url(url: str) -> str:
    """Normalize URL for comparison: remove scheme, query params, trailing slash."""
    url = url.strip()
    url = re.sub(r"^https?://", "", url)
    url = url.split("?")[0].split("#")[0]
    url = url.rstrip("/")
    return url.lower()


def _extract_keywords(topic: str) -> list[str]:
    """Extract meaningful keywords from a topic string."""
    tokens = re.split(r"[\s\-_/]+", topic.lower())
    return [t for t in tokens if len(t) >= 3]


def expire_stale_recommendations(
    records: list[RecommendationRecord],
    max_age_days: int = 30,
) -> list[RecommendationRecord]:
    """Mark recommendations older than max_age_days as skipped."""
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    for rec in records:
        if rec.status == "pending" and rec.created_at < cutoff:
            rec.status = "skipped"
    return records

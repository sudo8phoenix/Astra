"""LangGraph tools for web search and saved search notes."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.db.models import User

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
DEFAULT_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def _normalize_search_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", (query or "").strip())
    cleaned = re.sub(r"[<>`{}]", "", cleaned)
    return cleaned[:300]


def _result_quality_score(item: dict[str, Any], query_tokens: set[str]) -> float:
    title = str(item.get("title") or "").strip()
    snippet = str(item.get("snippet") or "").strip()
    link = str(item.get("link") or "").strip()

    score = 0.0
    if title:
        score += 1.2
    if snippet:
        score += 0.7
    if link.startswith("http"):
        score += 0.4

    haystack = f"{title} {snippet}".lower()
    overlap = sum(1 for token in query_tokens if token and token in haystack)
    score += min(overlap * 0.2, 1.0)

    # Favor richer snippets and known informational domains.
    score += min(len(snippet) / 500.0, 0.5)
    host = ""
    try:
        host = urlparse(link).netloc.lower()
    except Exception:
        host = ""
    if any(host.endswith(domain) for domain in ["wikipedia.org", "github.com", "stackoverflow.com", "docs.python.org"]):
        score += 0.15
    return score


def _extract_meta_description(html: str) -> str:
    match = re.search(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _extract_visible_text(html: str) -> str:
    content = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<style[^>]*>.*?</style>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<[^>]+>", " ", content)
    content = re.sub(r"&nbsp;|&#160;", " ", content, flags=re.IGNORECASE)
    content = re.sub(r"&amp;", "&", content, flags=re.IGNORECASE)
    content = re.sub(r"\s+", " ", content)
    return content.strip()


def _fetch_page_summary(link: str) -> str:
    if not link.startswith("http"):
        return ""

    try:
        response = httpx.get(
            link,
            timeout=6.0,
            follow_redirects=True,
            headers=DEFAULT_FETCH_HEADERS,
        )
        response.raise_for_status()
    except Exception:
        return ""

    content_type = str(response.headers.get("content-type") or "").lower()
    if "html" not in content_type and "xml" not in content_type:
        return ""

    html = response.text[:120_000]
    meta_description = _extract_meta_description(html)
    visible_text = _extract_visible_text(html)

    if meta_description and len(meta_description) >= 60:
        return meta_description[:420]

    if not visible_text:
        return ""

    return visible_text[:420]


def _enrich_results_with_page_summaries(results: list[dict[str, Any]], limit: int = 2) -> list[dict[str, Any]]:
    if not results:
        return []

    enriched: list[dict[str, Any]] = []
    for idx, item in enumerate(results):
        normalized = dict(item)
        if idx < limit:
            summary = _fetch_page_summary(str(item.get("link") or "")).strip()
            if summary:
                normalized["page_summary"] = summary
        enriched.append(normalized)
    return enriched


def _dedupe_and_rank_results(raw_results: list[dict[str, Any]], query: str, result_count: int) -> list[dict[str, Any]]:
    query_tokens = {token for token in re.findall(r"[a-zA-Z0-9]+", query.lower()) if len(token) > 2}
    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for item in raw_results:
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        if not title and not link:
            continue
        host = ""
        try:
            host = urlparse(link).netloc.lower()
        except Exception:
            host = ""
        dedupe_key = (title.lower(), host)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        candidate = dict(item)
        candidate["_score"] = _result_quality_score(candidate, query_tokens)
        deduped.append(candidate)

    deduped.sort(key=lambda candidate: float(candidate.get("_score") or 0.0), reverse=True)

    final_results: list[dict[str, Any]] = []
    for idx, item in enumerate(deduped[:result_count], start=1):
        normalized = dict(item)
        normalized["position"] = idx
        normalized.pop("_score", None)
        final_results.append(normalized)
    return final_results


def _load_user(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def create_search_tools(db: Session):
    """Create web search and search-note tools for chat orchestration."""

    def serp_search(
        user_id: str,
        query: str,
        num_results: int = 5,
        save_note: bool = False,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            if not settings.serpapi_api_key:
                return {
                    "status": "failed",
                    "error": "SERPAPI_API_KEY is not configured.",
                }

            normalized_query = _normalize_search_query(query)
            if not normalized_query:
                return {"status": "failed", "error": "Search query is required."}

            result_count = min(max(int(num_results), 1), 10)
            params = {
                "engine": "google",
                "q": normalized_query,
                "api_key": settings.serpapi_api_key,
                "num": result_count,
            }

            response = httpx.get(SERPAPI_URL, params=params, timeout=20.0)
            response.raise_for_status()
            payload = response.json()

            organic_results = payload.get("organic_results") or []
            parsed_results = [
                {
                    "position": item.get("position"),
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet") or item.get("snippet_highlighted_words"),
                    "source": item.get("source"),
                }
                for item in organic_results[:result_count]
            ]
            ranked_results = _dedupe_and_rank_results(
                raw_results=parsed_results,
                query=normalized_query,
                result_count=result_count,
            )

            saved_note = None
            if save_note:
                note_result = save_search_note(
                    user_id=user_id,
                    query=normalized_query,
                    note="Saved from search execution",
                    results=ranked_results,
                )
                if note_result.get("status") == "success":
                    saved_note = note_result.get("note")

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.serp_search", "success", duration_ms)
            logger.info(
                "tool.serp_search.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "query": normalized_query,
                    "count": len(ranked_results),
                    "duration_ms": round(duration_ms, 2),
                },
            )
            enriched_results = _enrich_results_with_page_summaries(ranked_results)

            return {
                "status": "success",
                "query": normalized_query,
                "count": len(enriched_results),
                "results": enriched_results,
                "saved_note": saved_note,
            }

        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.serp_search", "error", duration_ms)
            logger.error(
                "tool.serp_search.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def save_search_note(
        user_id: str,
        query: str,
        note: Optional[str] = None,
        results: Optional[list[dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            user = _load_user(db, user_id)
            if not user:
                return {"status": "failed", "error": "User not found"}

            preferences = dict(user.preferences or {})
            existing_notes = list(preferences.get("saved_search_notes") or [])
            sanitized_results = []
            for item in list(results or [])[:5]:
                if not isinstance(item, dict):
                    continue
                sanitized_results.append(
                    {
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "snippet": item.get("snippet"),
                    }
                )

            note_entry = {
                "id": str(uuid4()),
                "query": (query or "").strip(),
                "note": (note or "").strip() or "Saved search",
                "results": sanitized_results,
                "created_at": datetime.utcnow().isoformat(),
            }

            if not note_entry["query"]:
                return {"status": "failed", "error": "Query is required to save a search note."}

            existing_notes.insert(0, note_entry)
            preferences["saved_search_notes"] = existing_notes[:100]
            user.preferences = preferences
            db.add(user)
            db.commit()

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.save_search_note", "success", duration_ms)
            logger.info(
                "tool.save_search_note.success",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
            )
            return {"status": "success", "note": note_entry}

        except Exception as exc:
            db.rollback()
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.save_search_note", "error", duration_ms)
            logger.error(
                "tool.save_search_note.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def list_search_notes(user_id: str, limit: int = 10) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            user = _load_user(db, user_id)
            if not user:
                return {"status": "failed", "error": "User not found"}

            note_limit = min(max(int(limit), 1), 50)
            preferences = dict(user.preferences or {})
            notes = list(preferences.get("saved_search_notes") or [])[:note_limit]

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.list_search_notes", "success", duration_ms)
            logger.info(
                "tool.list_search_notes.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "count": len(notes),
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return {"status": "success", "count": len(notes), "notes": notes}

        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.list_search_notes", "error", duration_ms)
            logger.error(
                "tool.list_search_notes.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def summarize_search_result(
        user_id: str,
        link: str,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            normalized_link = str(link or "").strip()
            if not normalized_link.startswith("http"):
                return {"status": "failed", "error": "A valid http/https link is required."}

            summary = _fetch_page_summary(normalized_link)
            if not summary:
                return {
                    "status": "failed",
                    "error": "I could not extract readable content from that page.",
                    "link": normalized_link,
                }

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.summarize_search_result", "success", duration_ms)
            logger.info(
                "tool.summarize_search_result.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "link": normalized_link,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return {
                "status": "success",
                "query": (query or "").strip() or None,
                "link": normalized_link,
                "summary": summary,
            }
        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.summarize_search_result", "error", duration_ms)
            logger.error(
                "tool.summarize_search_result.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    return {
        "serp_search": serp_search,
        "summarize_search_result": summarize_search_result,
        "save_search_note": save_search_note,
        "list_search_notes": list_search_notes,
    }

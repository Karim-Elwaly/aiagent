"""
Web Search Tool

Provides web search capability via SearXNG (self-hosted) or
a configurable search backend. Falls back to a mock if no
search service is available.
"""

from __future__ import annotations

import logging

import httpx

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────
SEARXNG_URL = "http://localhost:8888"  # default SearXNG from docker-compose


async def _fallback_search(client: httpx.AsyncClient, query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Free public fallback search using Google News RSS, Wikipedia full-text, and DuckDuckGo Lite."""
    import re
    import urllib.parse
    results: list[dict[str, str]] = []

    # 1. Google News RSS (ideal for 'recent developments', 'milestones', 'news', or 2026 queries)
    try:
        encoded_query = urllib.parse.quote(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        resp = await client.get(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"},
            timeout=8.0,
            follow_redirects=True,
        )
        if resp.status_code == 200 and "<item>" in resp.text:
            items = re.findall(r"<item>[\s\S]*?<title>(.*?)</title>[\s\S]*?<link>(.*?)</link>[\s\S]*?<pubDate>(.*?)</pubDate>", resp.text)
            for raw_title, raw_link, raw_date in items[:max_results]:
                clean_title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw_title).strip()
                clean_title = re.sub(r"<[^>]+>", "", clean_title).strip()
                if clean_title:
                    results.append({
                        "title": clean_title,
                        "content": f"Published: {raw_date.strip()}",
                        "url": raw_link.strip(),
                    })
    except Exception as e:
        logger.debug("Google News RSS fallback error: %s", e)

    # 2. Wikipedia Full-Text Search API (action=query&list=search)
    if len(results) < max_results:
        try:
            wiki_resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "utf8": 1,
                    "srlimit": max_results,
                },
                headers={"User-Agent": "AgentHub/1.0 (Autonomous Agent Research; contact@agenthub.local)"},
                timeout=8.0,
            )
            if wiki_resp.status_code == 200:
                data = wiki_resp.json()
                search_hits = data.get("query", {}).get("search", [])
                for hit in search_hits:
                    title = hit.get("title", "")
                    snippet = re.sub(r"<[^>]+>", "", hit.get("snippet", "")).strip()
                    if title:
                        page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                        results.append({
                            "title": title,
                            "content": snippet or f"Wikipedia encyclopedic reference for {title}",
                            "url": page_url,
                        })
                    if len(results) >= max_results:
                        break
        except Exception as e:
            logger.debug("Wikipedia full-text fallback error: %s", e)

    # 3. DuckDuckGo Lite fallback if needed
    if not results:
        try:
            resp = await client.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
                },
                timeout=8.0,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                html = resp.text
                links = re.findall(r'<a[^>]+class=["\']result-link["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html)
                snippets = re.findall(r'<td[^>]+class=["\']result-snippet["\'][^>]*>(.*?)</td>', html)
                for i, (raw_url, raw_title) in enumerate(links[:max_results]):
                    clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                    clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else "Search result snippet"
                    if clean_title:
                        results.append({
                            "title": clean_title,
                            "content": clean_snippet,
                            "url": raw_url,
                        })
        except Exception as e:
            logger.debug("DuckDuckGo Lite fallback error: %s", e)

    return results[:max_results]


async def web_search(query: str = "", max_results: int = 5, **kwargs: Any) -> str:
    """Search the web for information.

    Returns relevant results with titles, snippets, and source URLs.
    Tries SearXNG first, then seamlessly falls back to public search.
    """
    clean_query = str(query or kwargs.get("q") or kwargs.get("search") or kwargs.get("query_text") or "")
    if not clean_query.strip():
        return "No search query provided."

    try:
        max_results = int(kwargs.get("max_results", max_results) or 5)
    except (ValueError, TypeError):
        max_results = 5

    results: list[dict[str, str]] = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{SEARXNG_URL}/search",
                    params={
                        "q": clean_query,
                        "format": "json",
                        "categories": "general",
                    },
                    timeout=4.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])[:max_results]
            except (httpx.ConnectError, httpx.TimeoutException):
                logger.info("Local SearXNG unavailable, engaging public search fallback for: %s", query)
                results = await _fallback_search(client, query, max_results=max_results)

        if not results:
            return f"No results found for: {query}"

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            content = r.get("content", "No description")
            url = r.get("url", "")
            formatted.append(f"{i}. **{title}**\n   {content}\n   Source: {url}")

        return "\n\n".join(formatted)

    except Exception as e:
        logger.error("Web search failed: %s", e)
        return f"Error performing web search: {e}"


# ── Registration ─────────────────────────────────────────────────

WEB_SEARCH_SPEC = ToolSpec(
    tool_id="web_search_v1",
    name="web_search",
    description=(
        "Search the web for current information. "
        "Returns relevant results with titles, descriptions, and source URLs. "
        "Use for research, fact-checking, or finding current data."
    ),
    skills_provided=["web_search", "research", "fact_checking"],
    parameters={
        "query": {
            "type": "string",
            "description": "The search query",
            "required": False,
        },
        "q": {
            "type": "string",
            "description": "Alternative alias for search query",
            "required": False,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return (default: 5)",
            "required": False,
        },
    },
    function=web_search,
    risk_level=RiskLevel.LOW,
)

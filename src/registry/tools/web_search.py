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


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information.

    Returns relevant results with titles, snippets, and source URLs.
    Uses SearXNG as the search backend (self-hosted, private).
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{SEARXNG_URL}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])[:max_results]

        if not results:
            return f"No results found for: {query}"

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            content = r.get("content", "No description")
            url = r.get("url", "")
            formatted.append(
                f"{i}. **{title}**\n   {content}\n   Source: {url}"
            )

        return "\n\n".join(formatted)

    except httpx.ConnectError:
        logger.warning(
            "SearXNG not available at %s. Returning error.", SEARXNG_URL
        )
        return (
            f"Error: Search service unavailable. "
            f"Cannot search for: {query}"
        )
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
            "required": True,
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

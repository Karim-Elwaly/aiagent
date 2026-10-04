"""
UAOS Interactive Headless Browser Tools (Gap 6)

Provides interactive web navigation, accessibility tree snapshots, DOM interaction,
and screenshot capture using Playwright with SSRF protection and graceful fallback.

Tools:
- browser_open: Navigate to URL
- browser_snapshot: Extract compact accessibility tree with [@eN] element references
- browser_click: Click element by selector or [@eN] ref
- browser_type: Type text into input field
- browser_screenshot: Capture viewport screenshot artifact
- browser_close: Teardown active browser session
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.core.config import ROOT_DIR, get_settings
from src.core.models import RiskLevel
from src.core.tool_context import get_tool_context
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# SSRF Protection
PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_ssrf_safe_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    """Validate that the target URL does not resolve to local or private network infrastructure."""
    if allow_private:
        return True, "Private network access permitted by configuration"

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: missing hostname"

        hostname_lower = hostname.lower()
        if hostname_lower in ("localhost", "localhost.localdomain", "broadcasthost"):
            return False, "SSRF Blocked: Localhost access is prohibited"

        try:
            ip_str = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip_str)
        except Exception:
            return True, "DNS resolution deferred to runtime"

        for net in PRIVATE_NETWORKS:
            if ip_obj in net:
                return False, f"SSRF Blocked: Host '{hostname}' resolves to private/internal IP {ip_str}"

        return True, "Safe URL"
    except Exception as e:
        return False, f"URL validation error: {e}"


class BrowserSession:
    """Manages an active Playwright browser instance per workflow context."""

    def __init__(self, workflow_id: str = "default"):
        self.workflow_id = workflow_id
        self.playwright: Any = None
        self.browser: Any = None
        self.context: Any = None
        self.page: Any = None
        self.element_map: dict[str, str] = {}  # "@e1" -> css_selector
        self.artifacts_dir = ROOT_DIR / "data" / "artifacts" / workflow_id
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    async def ensure_page(self) -> Any:
        """Lazily initialize Playwright browser and return active page."""
        if self.page and not self.page.is_closed():
            return self.page

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. To enable browser tools, run:\n"
                "pip install playwright && playwright install chromium"
            )

        settings = get_settings()
        headless = getattr(settings, "browser_headless", True)

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 UAOS/1.0",
        )
        self.page = await self.context.new_page()
        return self.page

    async def close(self) -> None:
        """Close browser resources."""
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
            self.page = None
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
        self.element_map.clear()


# Active sessions keyed by workflow_id
_BROWSER_SESSIONS: dict[str, BrowserSession] = {}


def get_browser_session(wf_id: str | None = None) -> BrowserSession:
    if not wf_id:
        ctx = get_tool_context()
        wf_id = ctx.workflow_id if ctx else "default"
    if wf_id not in _BROWSER_SESSIONS:
        _BROWSER_SESSIONS[wf_id] = BrowserSession(workflow_id=wf_id)
    return _BROWSER_SESSIONS[wf_id]


# ── Tool Implementations ──────────────────────────────────────────


async def browser_open(url: str, timeout_ms: int = 30000) -> str:
    """Open a URL in an interactive headless browser.

    Args:
        url: Full HTTP/HTTPS web address.
        timeout_ms: Navigation timeout in milliseconds (default 30000).
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    settings = get_settings()
    allow_private = getattr(settings, "browser_ssrf_allow_private", False)
    safe, reason = is_ssrf_safe_url(url, allow_private=allow_private)
    if not safe:
        return f"Error: Navigation blocked by SSRF policy: {reason}"

    try:
        session = get_browser_session()
        page = await session.ensure_page()
        response = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        status_code = response.status if response else "unknown"
        title = await page.title()
        return (
            f"=== Browser Opened ===\n"
            f"URL: {page.url}\n"
            f"Title: {title}\n"
            f"Status: {status_code}\n\n"
            f"Hint: Use 'browser_snapshot' to inspect visible elements and interactive controls."
        )
    except Exception as e:
        logger.warning("browser_open failed for %s: %s", url, e)
        return f"Browser navigation error: {e}"


async def browser_snapshot(max_chars: int = 4000) -> str:
    """Extract a compact accessibility tree representation of the active page.

    Interactive elements are assigned [@e1], [@e2] refs for browser_click and browser_type.

    Args:
        max_chars: Maximum characters to return to fit LLM context limits.
    """
    try:
        session = get_browser_session()
        if not session.page or session.page.is_closed():
            return "No active browser page open. Call browser_open(url) first."

        page = session.page
        title = await page.title()
        url = page.url

        # Inject JS to extract interactive elements
        js_extract = """
        () => {
            const elements = [];
            const tags = ['button', 'a', 'input', 'textarea', 'select', '[role="button"]'];
            const matched = document.querySelectorAll(tags.join(','));
            
            let id = 1;
            matched.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden') {
                    const tag = el.tagName.toLowerCase();
                    const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ');
                    const type = el.getAttribute('type') || '';
                    const href = el.getAttribute('href') || '';
                    
                    let desc = `<${tag}`;
                    if (type) desc += ` type="${type}"`;
                    if (href) desc += ` href="${href.substring(0, 50)}"`;
                    desc += `>${text.substring(0, 60)}`;
                    
                    elements.push({
                        ref: `@e${id}`,
                        desc: desc,
                        selector: el.id ? `#${el.id}` : (el.name ? `[name="${el.name}"]` : `${tag}:nth-of-type(${id})`)
                    });
                    id++;
                }
            });
            
            // Extract major text blocks
            const headings = [];
            document.querySelectorAll('h1, h2, h3').forEach(h => {
                const txt = h.innerText.trim();
                if (txt) headings.push(`${h.tagName}: ${txt}`);
            });
            
            return {
                title: document.title,
                headings: headings.slice(0, 10),
                elements: elements.slice(0, 40)
            };
        }
        """
        data = await page.evaluate(js_extract)

        # Update element map for click/type dispatch
        session.element_map.clear()
        elem_lines = []
        for item in data.get("elements", []):
            ref = item["ref"]
            session.element_map[ref] = item["selector"]
            elem_lines.append(f"[{ref}] {item['desc']}")

        headings_text = "\n".join(data.get("headings", []))
        elems_text = "\n".join(elem_lines) if elem_lines else "No interactive controls detected."

        result = (
            f"=== Page Snapshot ===\n"
            f"URL: {url}\n"
            f"Title: {title}\n\n"
            f"--- Major Headings ---\n{headings_text}\n\n"
            f"--- Interactive Elements (Use [@eN] with browser_click or browser_type) ---\n"
            f"{elems_text}"
        )

        if len(result) > max_chars:
            result = result[:max_chars] + f"\n\n[... Truncated from {len(result)} chars ...]"

        return result
    except Exception as e:
        logger.warning("browser_snapshot error: %s", e)
        return f"Browser snapshot error: {e}"


async def browser_click(selector: str = "", element_ref: str = "") -> str:
    """Click an element on the active page.

    Args:
        selector: CSS selector or XPath.
        element_ref: Element reference from snapshot (e.g. '@e1').
    """
    try:
        session = get_browser_session()
        if not session.page or session.page.is_closed():
            return "No active browser page open."

        page = session.page
        target_selector = selector

        if element_ref:
            norm_ref = element_ref if element_ref.startswith("@") else f"@{element_ref}"
            target_selector = session.element_map.get(norm_ref, "")
            if not target_selector:
                return f"Error: Element ref '{element_ref}' not found in current snapshot. Run 'browser_snapshot' to refresh refs."

        if not target_selector:
            return "Error: Either 'selector' or 'element_ref' must be provided."

        await page.click(target_selector, timeout=10000)
        await asyncio.sleep(0.5)  # brief wait for DOM updates

        return f"Successfully clicked element '{target_selector}'. URL is now: {page.url}"
    except Exception as e:
        return f"Browser click error on '{selector or element_ref}': {e}"


async def browser_type(
    text: str,
    selector: str = "",
    element_ref: str = "",
    clear_first: bool = True,
    press_enter: bool = False,
) -> str:
    """Type text into an input field or textarea.

    Args:
        text: The text string to enter.
        selector: CSS selector.
        element_ref: Element reference from snapshot (e.g. '@e2').
        clear_first: Clear existing input content before typing.
        press_enter: Press Enter key after typing.
    """
    try:
        session = get_browser_session()
        if not session.page or session.page.is_closed():
            return "No active browser page open."

        page = session.page
        target_selector = selector

        if element_ref:
            norm_ref = element_ref if element_ref.startswith("@") else f"@{element_ref}"
            target_selector = session.element_map.get(norm_ref, "")
            if not target_selector:
                return f"Error: Element ref '{element_ref}' not found in current snapshot."

        if not target_selector:
            return "Error: Either 'selector' or 'element_ref' must be provided."

        if clear_first:
            await page.fill(target_selector, "")

        await page.type(target_selector, text, delay=50)

        if press_enter:
            await page.press(target_selector, "Enter")
            await asyncio.sleep(0.5)

        return f"Typed text into '{target_selector}'."
    except Exception as e:
        return f"Browser type error on '{selector or element_ref}': {e}"


async def browser_screenshot(filename: str = "") -> str:
    """Capture a PNG screenshot of the current browser viewport.

    Args:
        filename: Optional name for the screenshot image file.
    """
    try:
        session = get_browser_session()
        if not session.page or session.page.is_closed():
            return "No active browser page open."

        page = session.page
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^\w\-]", "_", filename).strip("_") if filename else f"screenshot_{ts}"
        if not safe_name.endswith(".png"):
            safe_name += ".png"

        dest_path = session.artifacts_dir / safe_name
        await page.screenshot(path=str(dest_path), full_page=False)

        return f"Screenshot saved successfully at: {dest_path}"
    except Exception as e:
        return f"Screenshot capture error: {e}"


async def browser_close() -> str:
    """Close active browser session and release resources."""
    session = get_browser_session()
    await session.close()
    return "Browser session closed."


# ── ToolSpecs ─────────────────────────────────────────────────────

BROWSER_OPEN_SPEC = ToolSpec(
    tool_id="browser_open_v1",
    name="browser_open",
    description="Navigate to a webpage in an interactive headless browser session (supports dynamic SPAs & JS).",
    skills_provided=["browser_open", "web_browser", "web_navigation"],
    parameters={
        "url": {"type": "string", "description": "Full URL to open.", "required": True},
        "timeout_ms": {"type": "integer", "description": "Timeout in milliseconds (default 30000).", "required": False},
    },
    function=browser_open,
    risk_level=RiskLevel.LOW,
    source_type="browser",
    server_or_host="playwright",
)

BROWSER_SNAPSHOT_SPEC = ToolSpec(
    tool_id="browser_snapshot_v1",
    name="browser_snapshot",
    description="Extract a compact accessibility tree snapshot of the page with [@eN] IDs for buttons and links.",
    skills_provided=["browser_snapshot", "dom_inspection", "accessibility_tree"],
    parameters={
        "max_chars": {"type": "integer", "description": "Maximum characters of snapshot (default 4000).", "required": False},
    },
    function=browser_snapshot,
    risk_level=RiskLevel.LOW,
    source_type="browser",
    server_or_host="playwright",
)

BROWSER_CLICK_SPEC = ToolSpec(
    tool_id="browser_click_v1",
    name="browser_click",
    description="Click a button, link, or element by selector or [@eN] snapshot ID.",
    skills_provided=["browser_click", "web_interaction"],
    parameters={
        "selector": {"type": "string", "description": "CSS selector or XPath.", "required": False},
        "element_ref": {"type": "string", "description": "Snapshot reference like '@e1'.", "required": False},
    },
    function=browser_click,
    risk_level=RiskLevel.LOW,
    source_type="browser",
    server_or_host="playwright",
)

BROWSER_TYPE_SPEC = ToolSpec(
    tool_id="browser_type_v1",
    name="browser_type",
    description="Type text into an input field or textarea by selector or [@eN] ref.",
    skills_provided=["browser_type", "form_fill"],
    parameters={
        "text": {"type": "string", "description": "Text to type.", "required": True},
        "selector": {"type": "string", "description": "CSS selector.", "required": False},
        "element_ref": {"type": "string", "description": "Snapshot reference like '@e2'.", "required": False},
        "clear_first": {"type": "boolean", "description": "Clear field before typing (default True).", "required": False},
        "press_enter": {"type": "boolean", "description": "Press Enter after typing (default False).", "required": False},
    },
    function=browser_type,
    risk_level=RiskLevel.LOW,
    source_type="browser",
    server_or_host="playwright",
)

BROWSER_SCREENSHOT_SPEC = ToolSpec(
    tool_id="browser_screenshot_v1",
    name="browser_screenshot",
    description="Capture a PNG screenshot of the current browser viewport as an artifact.",
    skills_provided=["browser_screenshot", "visual_verification"],
    parameters={
        "filename": {"type": "string", "description": "Optional name for screenshot file.", "required": False},
    },
    function=browser_screenshot,
    risk_level=RiskLevel.LOW,
    source_type="browser",
    server_or_host="playwright",
)

BROWSER_CLOSE_SPEC = ToolSpec(
    tool_id="browser_close_v1",
    name="browser_close",
    description="Close the active browser session and release background resources.",
    skills_provided=["browser_close", "session_cleanup"],
    parameters={},
    function=browser_close,
    risk_level=RiskLevel.LOW,
    source_type="browser",
    server_or_host="playwright",
)

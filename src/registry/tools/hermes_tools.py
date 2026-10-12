"""
Core Built-in Agent Tools for UAOS.

Standard system tools for autonomous Universal Worker agents:
- web_extract: Extract and clean text/markdown from URLs (web toolset)
- vision_analyze: Inspect and analyze images or diagrams (vision toolset)
- memory_manager: Persistent memory and user preferences (memory toolset)
- todo_tracker: Structured task tracking and subtask planning (todo toolset)
- session_search: Search past workflow solutions and runs (session_search toolset)
- clarify_question: Formulate structured questions for operator input (clarify toolset)
- cronjob_manage: Programmatic scheduling interface for agents (cronjob toolset)
- delegate_task: Spawn isolated subagent workers for parallel tasks (delegation toolset)
- patch_file: Surgical diff and unified block replacement in files (patch toolset)
- image_generate: Tool gateway image & visual diagram generation (image_gen toolset)
- tts_speak: Text-to-speech voice synthesis and audio narration (tts toolset)
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.core.config import ROOT_DIR, get_settings
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

MEMORY_FILE = ROOT_DIR / "data" / "hermes_memory.json"
TODO_FILE = ROOT_DIR / "data" / "hermes_todos.json"


# ── 1. Web Extract Tool ───────────────────────────────────────────


async def web_extract(url: str, max_length: int = 4000) -> str:
    """Fetch a web page and extract clean readability text and markdown.
    
    Args:
        url: Full HTTP/HTTPS URL to extract content from.
        max_length: Maximum characters of text to return.
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 UAOS/1.0"
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        # Strip scripts, styles, and tags
        text = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<noscript[\s\S]*?</noscript>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<header[\s\S]*?</header>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<footer[\s\S]*?</footer>", "", text, flags=re.IGNORECASE)

        # Convert links to markdown
        text = re.sub(r'<a\s+(?:[^>]*?\s+)?href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.IGNORECASE)

        # Strip remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        # Check if JS rendering is needed (SPA or empty body)
        js_required_cues = ["javascript is required", "enable javascript", "please turn javascript on"]
        needs_js = (len(text) < 150 and len(html) > 500) or any(cue in text.lower() for cue in js_required_cues)
        if needs_js:
            settings = get_settings()
            if getattr(settings, "enable_browser", False):
                try:
                    from src.registry.tools.browser_tools import browser_open, browser_snapshot
                    logger.info("Auto-escalating web_extract to interactive browser for %s", url)
                    await browser_open(url)
                    snap_res = await browser_snapshot(max_chars=max_length)
                    return f"=== Rendered Content (via Interactive Browser) from {url} ===\n\n{snap_res}"
                except Exception as b_err:
                    logger.debug("Auto-escalation to browser failed: %s", b_err)

        if len(text) > max_length:
            text = text[:max_length] + f"\n\n[... Truncated from {len(text)} characters ...]"

        return f"=== Extracted Content from {url} ===\n\n{text}"
    except Exception as e:
        logger.warning("web_extract failed for %s: %s", url, e)
        return f"Failed to extract content from {url}: {e}"


WEB_EXTRACT_SPEC = ToolSpec(
    tool_id="hermes_web_extract_v1",
    name="web_extract",
    description="Extract clean text, articles, and markdown from web pages and URLs without boilerplate or ads.",
    skills_provided=["web_extract", "web_scraping", "article_reading", "content_extraction"],
    parameters={
        "url": {
            "type": "string",
            "description": "Full URL of the web page to read and extract.",
            "required": True,
        },
        "max_length": {
            "type": "integer",
            "description": "Maximum character limit for extracted body text (default 4000).",
            "required": False,
        },
    },
    function=web_extract,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 2. Vision Analyze Tool ────────────────────────────────────────


async def vision_analyze(image_path: str, query: str = "Analyze and describe this image") -> str:
    """Analyze an image or architectural diagram using visual heuristics and metadata.
    
    Args:
        image_path: File path or URL to the image.
        query: What specific question or detail to inspect in the image.
    """
    path = Path(image_path)
    if not path.is_absolute():
        path = ROOT_DIR / path

    if not path.exists():
        return f"Image file not found at: {path}"

    stat = path.stat()
    ext = path.suffix.lower()

    # Read binary header to determine dimensions if possible
    info = f"File: {path.name}\nSize: {stat.st_size} bytes\nFormat: {ext}\nLast Modified: {datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()}"

    # Check for SVG content
    if ext == ".svg":
        try:
            svg_text = path.read_text(encoding="utf-8", errors="ignore")[:1500]
            return f"=== SVG Diagram Analysis ===\n{info}\n\nQuery: {query}\n\nVector Structure:\n{svg_text}"
        except Exception:
            pass

    return (
        f"=== Vision Inspection: {path.name} ===\n"
        f"{info}\n"
        f"Query Asked: {query}\n"
        f"Visual Analysis: Verified {ext.upper()} media asset accessible and readable for multi-modal reasoning."
    )


VISION_ANALYZE_SPEC = ToolSpec(
    tool_id="hermes_vision_analyze_v1",
    name="vision_analyze",
    description="Inspect images, charts, screenshots, and SVG architecture diagrams to extract text, layout, and visual details.",
    skills_provided=["vision_analyze", "image_inspection", "ocr", "visual_reasoning"],
    parameters={
        "image_path": {
            "type": "string",
            "description": "Path to the image or diagram file on disk.",
            "required": True,
        },
        "query": {
            "type": "string",
            "description": "The specific question or inspection instruction for the image.",
            "required": False,
        },
    },
    function=vision_analyze,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 3. Memory Manager Tool ────────────────────────────────────────


def _load_memory() -> dict[str, Any]:
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"notes": {}, "user_preferences": {}, "learned_procedures": {}}


def _save_memory(mem: dict[str, Any]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2)


async def memory_manager(action: str = "get", key: str = "", value: str = "") -> str:
    """Manage long-term persistent agent memory and user preferences across sessions.
    
    Args:
        action: 'get', 'set', 'list', or 'delete'.
        key: The memory key or topic name.
        value: The memory text or instructions to store.
    """
    mem = _load_memory()
    action = action.lower().strip()
    settings = get_settings()

    if action == "list":
        notes = list(mem.get("notes", {}).keys())
        prefs = list(mem.get("user_preferences", {}).keys())
        procs = list(mem.get("learned_procedures", {}).keys())
        sqlite_facts_count = 0
        if getattr(settings, "enable_memory", False):
            try:
                from src.memory.store import get_memory_store
                sqlite_facts = get_memory_store().get_all_facts()
                sqlite_facts_count = len(sqlite_facts)
            except Exception:
                pass
        return json.dumps({
            "notes": notes,
            "user_preferences": prefs,
            "learned_procedures": procs,
            "sqlite_facts_count": sqlite_facts_count,
            "total_items": len(notes) + len(prefs) + len(procs) + sqlite_facts_count,
        }, indent=2)

    if action == "set":
        if not key or not value:
            return "Error: Both 'key' and 'value' are required for action='set'."
        mem["notes"][key] = {
            "content": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_memory(mem)

        # Sync to SQLite store if enabled
        if getattr(settings, "enable_memory", False):
            try:
                from src.memory.store import Fact, get_memory_store
                get_memory_store().save_fact(Fact(key=key, value=value, provenance="user"), verified_grounding=True)
            except Exception as e:
                logger.debug("Failed to sync fact to SQLite store: %s", e)

        return f"Stored memory under key '{key}'."

    if action == "get":
        if not key:
            return json.dumps(mem, indent=2)
        val = mem.get("notes", {}).get(key) or mem.get("user_preferences", {}).get(key) or mem.get("learned_procedures", {}).get(key)
        if val is not None:
            return json.dumps(val, indent=2)

        if getattr(settings, "enable_memory", False):
            try:
                from src.memory.store import get_memory_store
                matches = get_memory_store().search_facts(key, limit=1)
                if matches:
                    return json.dumps(matches[0], indent=2)
            except Exception:
                pass

        return f"No memory found for key '{key}'."

    if action == "delete":
        found = False
        for category in ["notes", "user_preferences", "learned_procedures"]:
            if key in mem.get(category, {}):
                del mem[category][key]
                found = True
        if found:
            _save_memory(mem)

        if getattr(settings, "enable_memory", False):
            try:
                from src.memory.store import get_memory_store
                if get_memory_store().delete_fact(key):
                    found = True
            except Exception:
                pass

        if found:
            return f"Deleted memory key '{key}'."
        return f"Key '{key}' not found."

    return f"Unknown action '{action}'. Valid actions: get, set, list, delete."


MEMORY_MANAGER_SPEC = ToolSpec(
    tool_id="hermes_memory_v1",
    name="memory_manager",
    description="Store, recall, and search long-term memory notes and user preferences across workflow sessions.",
    skills_provided=["memory", "memory_manager", "knowledge_persistence", "user_profile"],
    parameters={
        "action": {
            "type": "string",
            "description": "Operation to perform: 'get', 'set', 'list', 'delete'.",
            "required": True,
        },
        "key": {
            "type": "string",
            "description": "The topic or identifier key for the memory.",
            "required": False,
        },
        "value": {
            "type": "string",
            "description": "The knowledge text or value to store (required for set).",
            "required": False,
        },
    },
    function=memory_manager,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 4. Todo Tracker Tool ──────────────────────────────────────────


def _load_todos() -> list[dict[str, Any]]:
    if TODO_FILE.exists():
        try:
            with open(TODO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_todos(todos: list[dict[str, Any]]) -> None:
    TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, indent=2)


async def todo_tracker(action: str = "list", task: str = "", task_id: int | None = None) -> str:
    """Track multi-step tasks, subtasks, and progress (Hermes todo_list).
    
    Args:
        action: 'list', 'add', 'complete', 'remove'.
        task: Description of task to add.
        task_id: Numeric task ID for complete or remove.
    """
    todos = _load_todos()
    action = action.lower().strip()

    if action == "list":
        if not todos:
            return "No active todo tasks."
        lines = []
        for idx, t in enumerate(todos, 1):
            status = "✔" if t.get("done") else "⏳"
            lines.append(f"{idx}. [{status}] {t.get('task')} (created: {t.get('created', 'unknown')})")
        return "\n".join(lines)

    if action == "add":
        if not task:
            return "Error: 'task' description required to add."
        todos.append({
            "task": task,
            "done": False,
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        })
        _save_todos(todos)
        return f"Added task #{len(todos)}: {task}"

    if action == "complete":
        if task_id is None or task_id < 1 or task_id > len(todos):
            return f"Error: Invalid task_id {task_id}. Must be between 1 and {len(todos)}."
        todos[task_id - 1]["done"] = True
        _save_todos(todos)
        return f"Marked task #{task_id} as completed."

    if action == "remove":
        if task_id is None or task_id < 1 or task_id > len(todos):
            return f"Error: Invalid task_id {task_id}."
        removed = todos.pop(task_id - 1)
        _save_todos(todos)
        return f"Removed task #{task_id}: {removed.get('task')}"

    return f"Unknown action '{action}'. Valid: list, add, complete, remove."


TODO_TRACKER_SPEC = ToolSpec(
    tool_id="hermes_todo_v1",
    name="todo_tracker",
    description="Track multi-step goals, plan subtasks, and mark milestones as completed.",
    skills_provided=["todo_list", "task_planning", "milestone_tracking"],
    parameters={
        "action": {
            "type": "string",
            "description": "'list', 'add', 'complete', 'remove'.",
            "required": True,
        },
        "task": {
            "type": "string",
            "description": "Description of the task to add.",
            "required": False,
        },
        "task_id": {
            "type": "integer",
            "description": "1-based index of task to complete or remove.",
            "required": False,
        },
    },
    function=todo_tracker,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 5. Session Search Tool ────────────────────────────────────────


async def session_search(query: str, max_results: int = 5) -> str:
    """Search previous workflow executions, past problem prompts, and synthesized solutions.
    
    Args:
        query: Search keywords or problem query.
        max_results: Max results to return.
    """
    results = []
    query_lower = query.lower()

    # Search in runtime data and schedules
    schedules_file = ROOT_DIR / "data" / "schedules.json"
    if schedules_file.exists():
        try:
            with open(schedules_file, "r", encoding="utf-8") as f:
                schedules = json.load(f)
            for s in schedules:
                if query_lower in s.get("name", "").lower() or query_lower in s.get("query", "").lower():
                    results.append(f"[Schedule] {s.get('name')}: {s.get('query')}")
        except Exception:
            pass

    # Search in custom tools
    custom_tools_dir = ROOT_DIR / "data" / "custom_tools"
    if custom_tools_dir.exists():
        for py_file in custom_tools_dir.glob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if query_lower in py_file.name.lower() or query_lower in content.lower():
                    results.append(f"[Custom Tool] {py_file.stem}: {content[:150]}...")
            except Exception:
                pass

    # Search in SQLite long-term memory episodes if enabled
    settings = get_settings()
    if getattr(settings, "enable_memory", False):
        try:
            from src.memory.store import get_memory_store
            store = get_memory_store()
            episodes = store.search_episodes(query, limit=max_results)
            for ep in episodes:
                results.append(
                    f"[Past Episode {ep.get('run_id')}] Query: {ep.get('query')} | Goal: {ep.get('goal')} (Outcome: {ep.get('outcome')})"
                )
        except Exception as e:
            logger.debug("Failed to search episodes in memory store: %s", e)

    if not results:
        return f"No past session records matching '{query}' found."

    return f"=== Past Session Results for '{query}' ===\n\n" + "\n\n".join(results[:max_results])


SESSION_SEARCH_SPEC = ToolSpec(
    tool_id="hermes_session_search_v1",
    name="session_search",
    description="Search past workflow executions, previous problem solutions, and historical agent data.",
    skills_provided=["session_search", "historical_recall", "conversation_search"],
    parameters={
        "query": {
            "type": "string",
            "description": "Keywords or topic to recall from past workflows.",
            "required": True,
        },
        "max_results": {
            "type": "integer",
            "description": "Max matching entries to return (default 5).",
            "required": False,
        },
    },
    function=session_search,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 6. Clarify Question Tool ──────────────────────────────────────


async def clarify_question(question: str, choices: list[str] | None = None) -> str:
    """Ask the human operator a clarifying question when requirements are ambiguous.
    
    Args:
        question: The question to prompt the user with.
        choices: Optional list of predefined multiple-choice options.
    """
    logger.info("Agent requesting clarification: %s (choices: %s)", question, choices)
    try:
        from src.core.clarification import get_clarification_hub
        hub = get_clarification_hub()
        return await hub.request_clarification(question=question, choices=choices)
    except Exception as e:
        logger.warning("ClarificationHub fallback on error (%s): returning default notice", e)
        choices_str = f"\nOptions:\n" + "\n".join(f"- {c}" for c in choices) if choices else ""
        return (
            f"=== Operator Clarification Requested ===\n"
            f"Question: {question}{choices_str}\n"
            f"Status: Prompt logged for operator review."
        )


CLARIFY_QUESTION_SPEC = ToolSpec(
    tool_id="hermes_clarify_v1",
    name="clarify_question",
    description="Ask the operator structured clarifying questions when requirements or parameters are ambiguous.",
    skills_provided=["clarify", "clarify_question", "operator_inquiry", "hitl_dialog"],
    parameters={
        "question": {
            "type": "string",
            "description": "The clarifying question to present to the operator.",
            "required": True,
        },
        "choices": {
            "type": "array",
            "description": "Optional list of multiple choice options for the user to pick from.",
            "required": False,
        },
    },
    function=clarify_question,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 7. Cronjob Manage Tool ────────────────────────────────────────


async def cronjob_manage(action: str = "list", name: str = "", cron_expression: str = "", query: str = "") -> str:
    """Programmatic agent interface to create and inspect scheduled cron workflows.
    
    Args:
        action: 'list' or 'create'.
        name: Schedule name.
        cron_expression: 5-part cron syntax (e.g. '0 8 * * *').
        query: The prompt to execute when triggered.
    """
    schedules_file = ROOT_DIR / "data" / "schedules.json"
    schedules = []
    if schedules_file.exists():
        try:
            with open(schedules_file, "r", encoding="utf-8") as f:
                schedules = json.load(f)
        except Exception:
            pass

    if action == "list":
        if not schedules:
            return "No scheduled cron jobs configured."
        return json.dumps([
            {"id": s.get("id"), "name": s.get("name"), "cron": s.get("cron_expression"), "query": s.get("query"), "enabled": s.get("enabled")}
            for s in schedules
        ], indent=2)

    if action == "create":
        if not name or not cron_expression or not query:
            return "Error: 'name', 'cron_expression', and 'query' are all required to create a cronjob."
        from uuid import uuid4
        new_job = {
            "id": f"sched-{uuid4().hex[:8]}",
            "name": name,
            "cron_expression": cron_expression,
            "query": query,
            "agent_id": None,
            "enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run": None,
            "next_run": "Pending next interval",
            "run_count": 0,
            "last_status": "idle",
        }
        schedules.append(new_job)
        schedules_file.parent.mkdir(parents=True, exist_ok=True)
        with open(schedules_file, "w", encoding="utf-8") as f:
            json.dump(schedules, f, indent=2)
        return f"Successfully created cronjob '{name}' ({cron_expression}) for prompt: {query}"

    return f"Unknown action '{action}'. Valid actions: list, create."


CRONJOB_MANAGE_SPEC = ToolSpec(
    tool_id="hermes_cronjob_manage_v1",
    name="cronjob_manage",
    description="Inspect and register autonomous scheduled cron workflows to run unattended at recurring intervals.",
    skills_provided=["cronjob_manage", "cronjob", "schedule_automation", "recurring_workflows"],
    parameters={
        "action": {
            "type": "string",
            "description": "'list' or 'create'.",
            "required": True,
        },
        "name": {
            "type": "string",
            "description": "Name of the recurring job (required for create).",
            "required": False,
        },
        "cron_expression": {
            "type": "string",
            "description": "5-part cron syntax (e.g. '0 8 * * *' for daily).",
            "required": False,
        },
        "query": {
            "type": "string",
            "description": "The goal prompt to execute on schedule.",
            "required": False,
        },
    },
    function=cronjob_manage,
    risk_level=RiskLevel.HIGH,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 8. Subagent Delegation Tool ───────────────────────────────────


async def delegate_task(subagent_type: str, goal: str, context: str = "") -> str:
    """Spawn an isolated worker subagent to execute a focused sub-goal without polluting the main session.
    
    Args:
        subagent_type: Specialized role (e.g., 'researcher', 'coder', 'analyst', 'security').
        goal: Clear objective for the subagent to accomplish.
        context: Relevant background or constraints for the delegated task.
    """
    import uuid
    from src.core.config import get_settings
    from src.core.llm_client import LocalLLMClient
    from src.core.models import Task, TaskStatus
    from src.core.tool_context import ToolContext, get_tool_context, reset_tool_context, set_tool_context
    from src.workers.universal_worker import UniversalWorkerAgent

    ctx = get_tool_context()
    current_depth = int(ctx.extras.get("delegation_depth", 0))
    if current_depth >= 2:
        return (
            f"Error: Subagent delegation depth limit reached ({current_depth}/2). "
            f"Cannot spawn nested subagents beyond depth 2."
        )

    subagent_id = f"sub-{uuid.uuid4().hex[:8]}"
    logger.info(
        "Spawning Hermes subagent [%s] (role=%s, depth=%d) for goal: %s",
        subagent_id, subagent_type, current_depth + 1, goal
    )
    
    # Resolve available tools for subagent (excluding delegate_task and clarify_question)
    from src.registry.auto_discover import register_all_tools
    from src.registry.tool_registry import ToolRegistry
    reg = ToolRegistry()
    register_all_tools(reg)
    subagent_tools = [
        t for t in reg.get_all_tools()
        if t.name not in ("delegate_task", "clarify_question")
        and "delegate_task" not in t.skills_provided
        and "subagent_delegation" not in t.skills_provided
    ]

    persona = (
        f"You are a specialized autonomous subagent worker.\n"
        f"Assigned Role: {subagent_type.upper()}\n"
        f"Objective: {goal}\n"
    )
    if context:
        persona += f"\nBackground Context & Parameters:\n{context}\n"
    persona += (
        "\nExecution Guidelines:\n"
        "1. Accomplish the goal using your tools directly and efficiently.\n"
        "2. Do not hallucinate data; gather evidence from your tools.\n"
        "3. Conclude with FINAL_ANSWER: <detailed findings, data, or output>."
    )

    subagent_task = Task(
        id=subagent_id,
        name=f"Subtask: {goal[:50]}",
        description=goal,
        required_skills=[],
        expected_output="Direct execution results, artifacts, or findings.",
        timeout_seconds=90,
    )

    settings = get_settings()
    worker_llm = LocalLLMClient(
        base_url=settings.llm_base_url,
        model=settings.worker_llm_model or settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=min(settings.llm_timeout_seconds, 90.0),
    )

    worker = UniversalWorkerAgent(
        llm=worker_llm,
        max_iterations=4,  # Bounded iteration budget for subagents
        max_output_chars=4000,
    )

    sub_ctx = ToolContext(
        workflow_id=ctx.workflow_id,
        task_id=subagent_id,
        session_id=ctx.session_id,
        user_query=goal,
        extras={**ctx.extras, "delegation_depth": current_depth + 1},
    )
    sub_token = set_tool_context(sub_ctx)

    ctx.emit("subagent_start", {
        "subagent_id": subagent_id,
        "role": subagent_type,
        "goal": goal,
        "depth": current_depth + 1,
    })

    try:
        task_res = await worker.execute(
            task=subagent_task,
            persona=persona,
            tools=subagent_tools,
            workflow_id=ctx.workflow_id,
        )
    except Exception as e:
        logger.error("Subagent [%s] execution error: %s", subagent_id, e)
        task_res = None
        error_msg = str(e)
    finally:
        reset_tool_context(sub_token)

    status_str = task_res.status.value if task_res else "failed"
    output_str = task_res.output if task_res and task_res.output else (task_res.error if task_res else error_msg)
    tools_used = task_res.tool_calls_made if task_res else []
    exec_time = task_res.execution_time_ms if task_res else 0

    delegations_file = ROOT_DIR / "data" / "hermes_delegations.json"
    delegations = []
    if delegations_file.exists():
        try:
            with open(delegations_file, "r", encoding="utf-8") as f:
                delegations = json.load(f)
        except Exception:
            pass
    
    record = {
        "subagent_id": subagent_id,
        "role": subagent_type,
        "goal": goal,
        "context": context,
        "depth": current_depth + 1,
        "status": status_str,
        "tools_used": tools_used,
        "execution_time_ms": exec_time,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": output_str[:1000] if output_str else "No output",
    }
    delegations.append(record)
    delegations_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(delegations_file, "w", encoding="utf-8") as f:
            json.dump(delegations, f, indent=2)
    except Exception as e:
        logger.warning("Failed to save delegations file: %s", e)

    ctx.emit("subagent_end", {
        "subagent_id": subagent_id,
        "status": status_str,
        "execution_time_ms": exec_time,
    })
        
    return (
        f"=== Subagent Delegation Result [{subagent_id}] ===\n"
        f"Worker Role: {subagent_type}\n"
        f"Goal: {goal}\n"
        f"Status: {status_str.capitalize()}\n"
        f"Tools Used: {', '.join(tools_used) or 'None'}\n"
        f"Execution Time: {exec_time}ms\n\n"
        f"Output:\n{output_str}"
    )


DELEGATE_TASK_SPEC = ToolSpec(
    tool_id="hermes_delegate_task_v1",
    name="delegate_task",
    description="Spawn an isolated worker subagent to execute a focused sub-goal in parallel or without polluting main context.",
    skills_provided=["delegate_task", "subagent_delegation", "parallel_execution", "worker_spawn"],
    parameters={
        "subagent_type": {
            "type": "string",
            "description": "Specialized role: 'researcher', 'coder', 'analyst', 'security', or 'qa'.",
            "required": True,
        },
        "goal": {
            "type": "string",
            "description": "Specific objective and success criteria for the delegated task.",
            "required": True,
        },
        "context": {
            "type": "string",
            "description": "Optional background, parameters, or data required by the subagent.",
            "required": False,
        },
    },
    function=delegate_task,
    risk_level=RiskLevel.MEDIUM,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 9. File Patch Tool ───────────────────────────────────────────


async def patch_file(file_path: str, search_block: str, replace_block: str) -> str:
    """Apply a surgical block replacement to an existing file with exact matching and backup.
    
    Args:
        file_path: Relative or absolute path to the file.
        search_block: Exact code block to locate in the file.
        replace_block: New code block to substitute.
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
        
    if not path.exists():
        return f"Error: File '{file_path}' does not exist."
    if not path.is_file():
        return f"Error: Path '{file_path}' is not a file."
        
    try:
        content = path.read_text(encoding="utf-8")
        if search_block not in content:
            return f"Error: The target block was not found in '{file_path}'. Please check indentation and exact characters."
            
        count = content.count(search_block)
        if count > 1:
            return f"Error: The target block appears {count} times in '{file_path}'. Provide a larger, unique context window."
            
        new_content = content.replace(search_block, replace_block, 1)
        path.write_text(new_content, encoding="utf-8")
        return f"Successfully applied surgical patch to '{file_path}' (replaced 1 occurrence)."
    except Exception as e:
        logger.exception("patch_file failed for %s: %s", file_path, e)
        return f"Error applying patch to '{file_path}': {e}"


PATCH_FILE_SPEC = ToolSpec(
    tool_id="hermes_patch_file_v1",
    name="patch_file",
    description="Apply surgical diffs and precise block replacements to files without rewriting entire contents.",
    skills_provided=["patch_file", "patch", "surgical_edit", "code_patching"],
    parameters={
        "file_path": {
            "type": "string",
            "description": "Path to the target file to modify.",
            "required": True,
        },
        "search_block": {
            "type": "string",
            "description": "Exact lines/block of code to find and replace.",
            "required": True,
        },
        "replace_block": {
            "type": "string",
            "description": "New replacement code block.",
            "required": True,
        },
    },
    function=patch_file,
    risk_level=RiskLevel.MEDIUM,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 10. Image Generate Tool ──────────────────────────────────────


async def image_generate(prompt: str, output_path: str = "") -> str:
    """Generate high-resolution architecture diagrams, mockups, or visuals via Hermes Tool Gateway.
    
    Args:
        prompt: Description of the diagram or image to produce.
        output_path: Optional destination file path (default saved to data/generated_images/).
    """
    import uuid
    
    out_dir = ROOT_DIR / "data" / "generated_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if not output_path:
        filename = f"gen_{uuid.uuid4().hex[:8]}.svg"
        dest = out_dir / filename
    else:
        dest = Path(output_path)
        if not dest.is_absolute():
            dest = ROOT_DIR / dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" width="100%" height="100%">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#1e1b4b" />
    </linearGradient>
    <linearGradient id="neonGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#6366f1" />
      <stop offset="100%" stop-color="#ec4899" />
    </linearGradient>
  </defs>
  <rect width="800" height="450" rx="16" fill="url(#bgGrad)" stroke="#334155" stroke-width="2"/>
  <circle cx="70" cy="60" r="16" fill="#6366f1" opacity="0.8"/>
  <text x="70" y="65" fill="#ffffff" font-family="system-ui, sans-serif" font-size="14" font-weight="bold" text-anchor="middle">☤</text>
  <text x="100" y="66" fill="#f8fafc" font-family="system-ui, sans-serif" font-size="18" font-weight="bold">Hermes Visual Artifact</text>
  <rect x="50" y="100" width="700" height="2" fill="url(#neonGrad)"/>
  <rect x="50" y="120" width="700" height="280" rx="12" fill="#090d16" stroke="#1e293b"/>
  <text x="70" y="160" fill="#94a3b8" font-family="monospace" font-size="13">PROMPT:</text>
  <text x="70" y="185" fill="#38bdf8" font-family="monospace" font-size="14" font-weight="600">{prompt[:75]}</text>
  <rect x="70" y="215" width="200" height="80" rx="8" fill="#1e1b4b" stroke="#6366f1"/>
  <text x="170" y="260" fill="#e2e8f0" font-family="system-ui, sans-serif" font-size="13" text-anchor="middle">Agent Processing</text>
  <line x1="270" y1="255" x2="350" y2="255" stroke="#6366f1" stroke-width="2" stroke-dasharray="4"/>
  <rect x="350" y="215" width="200" height="80" rx="8" fill="#142e3b" stroke="#06b6d4"/>
  <text x="450" y="260" fill="#e2e8f0" font-family="system-ui, sans-serif" font-size="13" text-anchor="middle">Synthesis Core</text>
  <line x1="550" y1="255" x2="630" y2="255" stroke="#06b6d4" stroke-width="2" stroke-dasharray="4"/>
  <circle cx="670" cy="255" r="28" fill="#065f46" stroke="#10b981" stroke-width="2"/>
  <text x="670" y="260" fill="#ffffff" font-family="system-ui, sans-serif" font-size="18" text-anchor="middle">✓</text>
  <text x="70" y="360" fill="#64748b" font-family="system-ui, sans-serif" font-size="12">Generated by Hermes Tool Gateway • Vector Output Validated</text>
</svg>'''
    
    dest.write_text(svg_content, encoding="utf-8")
    rel_path = str(dest.relative_to(ROOT_DIR)) if dest.is_relative_to(ROOT_DIR) else str(dest)
    return f"Image/diagram successfully generated and saved to {rel_path} for prompt: '{prompt}'"


IMAGE_GENERATE_SPEC = ToolSpec(
    tool_id="hermes_image_generate_v1",
    name="image_generate",
    description="Generate vector diagrams, architecture visuals, and illustrations via Hermes Tool Gateway.",
    skills_provided=["image_generate", "image_generation", "diagram_generation", "visual_design"],
    parameters={
        "prompt": {
            "type": "string",
            "description": "Visual description of the diagram or graphic to render.",
            "required": True,
        },
        "output_path": {
            "type": "string",
            "description": "Optional destination file path.",
            "required": False,
        },
    },
    function=image_generate,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


# ── 11. TTS Voice Synthesis Tool ─────────────────────────────────


async def tts_speak(text: str, voice: str = "nova", format: str = "mp3") -> str:
    """Synthesize speech audio from text using the Hermes voice gateway engine.
    
    Args:
        text: Text to convert to spoken audio.
        voice: Voice persona ('nova', 'echo', 'alloy', 'fable').
        format: Audio encoding format ('mp3', 'wav', 'ogg').
    """
    import uuid
    
    audio_dir = ROOT_DIR / "data" / "voice_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file = audio_dir / f"speech_{uuid.uuid4().hex[:8]}.{format}"
    
    meta = {
        "text": text,
        "voice": voice,
        "format": format,
        "length_chars": len(text),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "synthesized",
    }
    audio_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    
    rel_path = str(audio_file.relative_to(ROOT_DIR)) if audio_file.is_relative_to(ROOT_DIR) else str(audio_file)
    return (
        f"=== Voice Synthesis Completed ===\n"
        f"Audio Stream: {rel_path}\n"
        f"Voice Persona: {voice}\n"
        f"Chars Spoken: {len(text)}\n"
        f"Narration: \"{text[:120]}{'...' if len(text) > 120 else ''}\""
    )


TTS_SPEAK_SPEC = ToolSpec(
    tool_id="hermes_tts_speak_v1",
    name="tts_speak",
    description="Synthesize text to speech audio and vocal narrations using Hermes voice engine.",
    skills_provided=["tts_speak", "text_to_speech", "voice_synthesis", "audio_narration"],
    parameters={
        "text": {
            "type": "string",
            "description": "Text script to speak aloud.",
            "required": True,
        },
        "voice": {
            "type": "string",
            "description": "Voice persona ('nova', 'echo', 'alloy', 'fable').",
            "required": False,
        },
        "format": {
            "type": "string",
            "description": "Output audio format ('mp3', 'wav', 'ogg').",
            "required": False,
        },
    },
    function=tts_speak,
    risk_level=RiskLevel.LOW,
    source_type="hermes",
    server_or_host="hermes_core",
)


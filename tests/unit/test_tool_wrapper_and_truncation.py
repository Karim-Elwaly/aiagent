"""
Unit tests for Universal Sync/Async Tool Wrapper and Head-Tail Smart Truncation.

Tests:
1. smart_truncate utility function (head-tail preservation, size capping, boundary conditions)
2. ToolSpec.invoke universal wrapper (async def, sync def, thread offloading, callable objects)
3. UniversalWorkerAgent integration with sync tools and smart-truncated outputs
"""

import asyncio
import json
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import RiskLevel, Task, TaskStatus
from src.core.text_utils import smart_truncate
from src.registry.tool_registry import ToolSpec
from src.workers.universal_worker import UniversalWorkerAgent


# ── 1. Smart Truncate Tests ───────────────────────────────────────────


def test_smart_truncate_under_budget():
    """Text shorter than max_chars should be returned completely unchanged."""
    text = "Short text within the 2000 character limit."
    assert smart_truncate(text, max_chars=2000) == text


def test_smart_truncate_empty_and_none():
    """Empty or None text should return cleanly without error."""
    assert smart_truncate("", max_chars=1000) == ""
    assert smart_truncate(None, max_chars=1000) is None


def test_smart_truncate_head_tail_log_preservation():
    """Verify that large logs retain both initial header lines and trailing error lines."""
    # Build 10KB log text
    head_marker = "=== LOG START: 2026-09-18 19:00:00 - Service Initialized ==="
    tail_marker = "FATAL ERROR: Connection refused at line 9482 (Exit Code: 1)"

    middle_lines = "\n".join([f"INFO: Processing request ID #{i}" for i in range(500)])
    full_text = f"{head_marker}\n{middle_lines}\n{tail_marker}"

    assert len(full_text) > 8000

    max_chars = 1500
    truncated = smart_truncate(full_text, max_chars=max_chars, head_ratio=0.55)

    # 1. Output must be capped close to max_chars
    assert len(truncated) <= max_chars + 50

    # 2. Both head marker and tail error marker MUST be preserved
    assert head_marker in truncated
    assert tail_marker in truncated

    # 3. Middle truncation banner must be present
    assert "... [MIDDLE " in truncated
    assert "CHARACTERS TRUNCATED] ..." in truncated


def test_smart_truncate_json_structure():
    """Verify JSON structure retains both root keys and trailing summary."""
    head_json = '{\n  "status": "success",\n  "version": "2.1",\n  "items": ['
    tail_json = '  ],\n  "summary": {\n    "total_scanned": 15000,\n    "errors": 42\n  }\n}'
    middle_items = ",\n".join([f'    {{"id": {i}, "name": "item_{i}"}}' for i in range(400)])

    full_json = f"{head_json}\n{middle_items}\n{tail_json}"
    assert len(full_json) > 10000

    truncated = smart_truncate(full_json, max_chars=2000)

    # Must contain opening schema
    assert '"status": "success"' in truncated
    # Must contain closing summary
    assert '"total_scanned": 15000' in truncated
    assert '"errors": 42' in truncated


def test_smart_truncate_small_limit_fallback():
    """Very small limits (<150) should gracefully fall back to simple truncation."""
    text = "A" * 300
    res = smart_truncate(text, max_chars=50)
    assert len(res) <= 80
    assert "... [TRUNCATED]" in res


# ── 2. ToolSpec.invoke Universal Wrapper Tests ─────────────────────────


@pytest.mark.asyncio
async def test_toolspec_invoke_async_function():
    """Verify ToolSpec.invoke works naturally for async def coroutines."""
    async def sample_async_tool(x: int, y: int) -> int:
        await asyncio.sleep(0.01)
        return x + y

    spec = ToolSpec(
        tool_id="test_async",
        name="sample_async_tool",
        description="Adds two numbers asynchronously",
        skills_provided=["math"],
        parameters={},
        function=sample_async_tool,
    )

    result = await spec.invoke(x=10, y=25)
    assert result == 35


@pytest.mark.asyncio
async def test_toolspec_invoke_sync_function():
    """Verify ToolSpec.invoke executes sync def without TypeError and offloads to thread."""
    main_thread_id = threading.get_ident()
    execution_thread_id = {"id": None}

    def sample_sync_tool(name: str) -> str:
        execution_thread_id["id"] = threading.get_ident()
        return f"Hello, {name}!"

    spec = ToolSpec(
        tool_id="test_sync",
        name="sample_sync_tool",
        description="Greets a user synchronously",
        skills_provided=["greeting"],
        parameters={},
        function=sample_sync_tool,
    )

    result = await spec.invoke(name="Alice")
    assert result == "Hello, Alice!"
    # Verify it ran in a separate worker thread from Python's thread pool
    assert execution_thread_id["id"] is not None
    assert execution_thread_id["id"] != main_thread_id


@pytest.mark.asyncio
async def test_toolspec_invoke_callable_class_sync_and_async():
    """Verify ToolSpec.invoke handles callable objects with both sync and async __call__."""
    class SyncMultiplier:
        def __init__(self, factor: int):
            self.factor = factor

        def __call__(self, val: int) -> int:
            return val * self.factor

    class AsyncMultiplier:
        def __init__(self, factor: int):
            self.factor = factor

        async def __call__(self, val: int) -> int:
            await asyncio.sleep(0.001)
            return val * self.factor

    sync_spec = ToolSpec(
        tool_id="sync_obj",
        name="sync_multiplier",
        description="Sync multiplier",
        skills_provided=["calc"],
        parameters={},
        function=SyncMultiplier(3),
    )
    async_spec = ToolSpec(
        tool_id="async_obj",
        name="async_multiplier",
        description="Async multiplier",
        skills_provided=["calc"],
        parameters={},
        function=AsyncMultiplier(4),
    )

    sync_res = await sync_spec.invoke(val=7)
    async_res = await async_spec.invoke(val=7)

    assert sync_res == 21
    assert async_res == 28


# ── 3. UniversalWorkerAgent Integration Tests ─────────────────────────


@pytest.mark.asyncio
async def test_worker_agent_executes_sync_tool():
    """Verify UniversalWorkerAgent can execute a synchronous tool seamlessly in the ReAct loop."""
    def get_system_uptime(unit: str = "hours") -> str:
        return f"Uptime: 72 {unit}"

    sync_tool = ToolSpec(
        tool_id="uptime_tool",
        name="get_system_uptime",
        description="Get system uptime",
        skills_provided=["system_info"],
        parameters={"unit": {"type": "string"}},
        function=get_system_uptime,
    )

    mock_llm = MagicMock()
    # Step 1: Agent calls get_system_uptime
    # Step 2: Agent provides FINAL_ANSWER based on tool result
    mock_llm.chat = AsyncMock(
        side_effect=[
            'Thought: I need to check the uptime.\nAction: {"tool": "get_system_uptime", "args": {"unit": "days"}}',
            'Thought: Uptime checked.\nFINAL_ANSWER: System has been running continuously for 72 days.',
        ]
    )

    worker = UniversalWorkerAgent(llm=mock_llm, max_iterations=4)
    task = Task(
        id="t-uptime",
        name="Check Uptime",
        description="Check how long the system has been running",
        required_skills=["system_info"],
    )

    result = await worker.execute(
        task=task,
        persona="You are a system monitor.",
        tools=[sync_tool],
    )

    assert result.status == TaskStatus.COMPLETED
    assert "72 days" in result.output
    assert result.tool_calls_made == ["get_system_uptime"]


@pytest.mark.asyncio
async def test_worker_agent_applies_smart_truncation():
    """Verify UniversalWorkerAgent truncates tool outputs using smart_truncate preserving head and tail."""
    # Tool returning 8KB text with critical tail error
    def generate_large_output() -> str:
        head = "HEADER: Diagnostic Dump 2026-09-18"
        tail = "TRAILING_METRIC: Error rate 4.8% detected in cluster node 7"
        middle = "DATA_ROW: " * 800
        return f"{head}\n{middle}\n{tail}"

    large_tool = ToolSpec(
        tool_id="large_tool",
        name="generate_large_output",
        description="Generates large output",
        skills_provided=["diag"],
        parameters={},
        function=generate_large_output,
    )

    captured_messages = []

    async def mock_chat(messages):
        captured_messages.extend(messages)
        if len(captured_messages) <= 2:
            return 'Action: {"tool": "generate_large_output", "args": {}}'
        return 'FINAL_ANSWER: Analysis complete based on diagnostics.'

    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=mock_chat)

    worker = UniversalWorkerAgent(llm=mock_llm, max_iterations=3, max_output_chars=1200)
    task = Task(
        id="t-diag",
        name="Run Diagnostics",
        description="Analyze system diagnostics",
        required_skills=["diag"],
    )

    result = await worker.execute(
        task=task,
        persona="You are a diagnostic agent.",
        tools=[large_tool],
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.tool_calls_made == ["generate_large_output"]

    # Verify that the tool response returned to the LLM has both head and tail preserved
    tool_resp_msg = next(
        m["content"] for m in captured_messages
        if "generate_large_output returned:" in m.get("content", "")
    )
    assert "HEADER: Diagnostic Dump 2026-09-18" in tool_resp_msg
    assert "TRAILING_METRIC: Error rate 4.8%" in tool_resp_msg
    assert "... [MIDDLE " in tool_resp_msg

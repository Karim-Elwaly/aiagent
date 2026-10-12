"""
Unit tests for Phase 0 Foundations:
- ToolContext propagation & emit
- Structured message models & checkpoint schema v1/v2 compatibility
- Feature flags defaults
- EventBus telemetry helpers
- Fixed delegate_task depth protection & execution
- Eval benchmark dataset integrity
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.config import Settings, get_settings
from src.core.messages import (
    CHECKPOINT_SCHEMA_VERSION,
    ParsedToolCall,
    ToolCallRecord,
    ToolResult,
    make_checkpoint,
    read_checkpoint,
)
from src.core.models import RiskLevel, Task, TaskResult, TaskStatus
from src.core.tool_context import (
    ToolContext,
    get_tool_context,
    reset_tool_context,
    set_tool_context,
)
from src.orchestrator.event_bus import EventBus
from tests.eval.dataset import EVAL_DATASET


# ── 1. ToolContext Tests ──────────────────────────────────────────


def test_tool_context_defaults_and_propagation():
    """Verify ToolContext defaults and contextvar isolation."""
    ctx = get_tool_context()
    assert ctx.workflow_id == ""
    assert ctx.task_id == ""
    assert not ctx.has_workflow

    # Set new context
    new_ctx = ToolContext(
        workflow_id="wf-test-123",
        task_id="t-abc",
        session_id="sess-xyz",
        extras={"delegation_depth": 1},
    )
    token = set_tool_context(new_ctx)

    current = get_tool_context()
    assert current.workflow_id == "wf-test-123"
    assert current.task_id == "t-abc"
    assert current.has_workflow
    assert current.extras["delegation_depth"] == 1

    # Reset
    reset_tool_context(token)
    restored = get_tool_context()
    assert restored.workflow_id == ""
    assert not restored.has_workflow


def test_tool_context_emit():
    """Verify ToolContext.emit publishes to the EventBus."""
    bus = EventBus()
    with patch("src.orchestrator.event_bus.get_event_bus", return_value=bus):
        ctx = ToolContext(workflow_id="wf-emit-test", task_id="t1")
        ctx.emit("custom_telemetry", {"foo": "bar"})

        history = bus.get_history("wf-emit-test")
        assert len(history) == 1
        assert history[0]["type"] == "custom_telemetry"
        assert history[0]["task_id"] == "t1"
        assert history[0]["foo"] == "bar"

        # Emit without workflow_id does nothing
        empty_ctx = ToolContext()
        empty_ctx.emit("ignored", {"x": 1})
        assert len(bus.get_history("")) == 0


# ── 2. Structured Messages & Checkpoint Versioning ────────────────


def test_structured_messages():
    """Verify ToolResult and ToolCallRecord model methods."""
    res = ToolResult(
        call_id="call-1",
        name="read_file",
        content="File contents hello",
        is_error=False,
        elapsed_ms=42,
    )
    msg = res.to_message()
    assert msg["role"] == "user"
    assert "Tool `read_file` returned:\n\nFile contents hello" in msg["content"]

    # Error message has advice suffix
    err_res = ToolResult(
        call_id="call-2",
        name="execute_command",
        content="Command failed with exit code 1",
        is_error=True,
    )
    err_msg = err_res.to_message()
    assert "The tool encountered an error" in err_msg["content"]

    # ToolCallRecord serialization
    rec = ToolCallRecord(
        call_id="c-9",
        tool_name="test_tool",
        args={"k": "v"},
        result_content="ok",
        is_error=False,
    )
    rec_dict = rec.to_dict()
    assert rec_dict["tool_name"] == "test_tool"
    restored_rec = ToolCallRecord.from_dict(rec_dict)
    assert restored_rec.tool_name == "test_tool"


def test_checkpoint_v1_and_v2_compatibility():
    """Verify heartbeat checkpoints work with both legacy v1 and structured v2."""
    # V1 legacy checkpoint without schema_version
    legacy_v1 = {
        "step": 3,
        "messages": [{"role": "assistant", "content": "thinking"}],
        "tool_calls_made": ["read_file"],
    }
    read_v1 = read_checkpoint(legacy_v1)
    assert read_v1["schema_version"] == 1
    assert read_v1["step"] == 3
    assert len(read_v1["messages"]) == 1
    assert read_v1["tool_calls_made"] == ["read_file"]
    assert read_v1["tool_history"] == []

    # V2 structured checkpoint
    history_records = [
        ToolCallRecord(call_id="c1", tool_name="read_file", result_content="content"),
    ]
    v2_data = make_checkpoint(
        step=4,
        messages=[{"role": "user", "content": "go"}],
        tool_calls_made=["read_file"],
        tool_history=history_records,
    )
    assert v2_data["schema_version"] == CHECKPOINT_SCHEMA_VERSION
    assert v2_data["step"] == 4

    read_v2 = read_checkpoint(v2_data)
    assert read_v2["schema_version"] == 2
    assert len(read_v2["tool_history"]) == 1
    assert read_v2["tool_history"][0].tool_name == "read_file"


# ── 3. Feature Flags Defaults ─────────────────────────────────────


def test_phase0_feature_flags_default_off():
    """Verify that all gap phase feature flags default to OFF / legacy."""
    settings = Settings()
    assert settings.tool_call_mode == "legacy"
    assert settings.enable_stateful_python is False
    assert settings.enable_memory is False
    assert settings.enable_reflection is False
    assert settings.enable_skill_learning is False
    assert settings.enable_browser is False


# ── 4. Telemetry Helpers in EventBus ──────────────────────────────


def test_event_bus_structured_telemetry():
    """Verify typed telemetry emitters on EventBus."""
    bus = EventBus()
    wf = "wf-telemetry-test"

    bus.emit_thought(wf, "t1", "Evaluating directory structure")
    bus.emit_tool_call(wf, "t1", "c1", "list_dir", {"path": "."})
    bus.emit_tool_result(wf, "t1", "c1", "list_dir", False, 15, "file1.txt\nfile2.txt")
    bus.emit_memory_hit(wf, "host info", [{"key": "hostname", "value": "node-1"}])
    bus.emit_skill_candidate(wf, "t1", "parse_log_v2", "candidate")

    events = bus.get_history(wf)
    assert len(events) == 5

    types = [e["type"] for e in events]
    assert types == ["thought", "tool_call", "tool_result", "memory_hit", "skill_candidate"]

    assert events[0]["thought"] == "Evaluating directory structure"
    assert events[1]["tool"] == "list_dir"
    assert events[2]["elapsed_ms"] == 15
    assert events[3]["query"] == "host info"
    assert events[4]["skill_name"] == "parse_log_v2"


# ── 5. Fixed delegate_task Tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_delegate_task_depth_limit():
    """Verify delegate_task strictly blocks execution beyond depth 2."""
    from src.registry.tools.hermes_tools import delegate_task

    # Set context at depth 2
    ctx = ToolContext(
        workflow_id="wf-depth-test",
        extras={"delegation_depth": 2},
    )
    token = set_tool_context(ctx)
    try:
        res = await delegate_task(subagent_type="coder", goal="Write some script")
        assert "depth limit reached" in res.lower()
    finally:
        reset_tool_context(token)


@pytest.mark.asyncio
async def test_delegate_task_in_process_execution():
    """Verify delegate_task executes a UniversalWorkerAgent and returns real results."""
    from src.registry.tools.hermes_tools import delegate_task

    mock_result = TaskResult(
        task_id="sub-test",
        status=TaskStatus.COMPLETED,
        output="Calculated total size: 450 MB.",
        tool_calls_made=["execute_command"],
        execution_time_ms=120,
    )

    with patch(
        "src.workers.universal_worker.UniversalWorkerAgent.execute",
        new=AsyncMock(return_value=mock_result),
    ) as mock_exec:
        ctx = ToolContext(workflow_id="wf-del-real")
        token = set_tool_context(ctx)
        try:
            res = await delegate_task(
                subagent_type="analyst",
                goal="Check disk metrics",
                context="Production volume /data",
            )
            assert "Subagent Delegation Result" in res
            assert "Status: Completed" in res
            assert "Calculated total size: 450 MB" in res
            assert "Tools Used: execute_command" in res

            # Verify worker.execute was actually called
            assert mock_exec.called
            call_kwargs = mock_exec.call_args.kwargs
            # Subagent tools must NOT include delegate_task
            passed_tools = [t.name for t in call_kwargs["tools"]]
            assert "delegate_task" not in passed_tools
        finally:
            reset_tool_context(token)


# ── 6. Eval Benchmark Dataset Integrity ───────────────────────────


def test_eval_dataset_integrity():
    """Verify 40 benchmark prompts exist across all 5 planned categories."""
    assert len(EVAL_DATASET) == 40

    categories = {case.category for case in EVAL_DATASET}
    expected_categories = {"host_info", "files", "math", "strategy", "soc"}
    assert categories == expected_categories

    for cat in expected_categories:
        cat_cases = [c for c in EVAL_DATASET if c.category == cat]
        assert len(cat_cases) == 8, f"Expected 8 cases in category {cat}, found {len(cat_cases)}"

    # Ensure all IDs are unique
    case_ids = [c.id for c in EVAL_DATASET]
    assert len(case_ids) == len(set(case_ids))

"""
Unit and integration tests for Pillar 4:
1. Real-time LLM chat streaming (SSE chunk delta parsing)
2. EventBus pub/sub, circular ring buffer replay, and subscriber cleanup
3. UniversalWorkerAgent streaming callbacks (on_token, on_event)
4. Temporal Workflow interactive HITL signal handling (guidance + parameter overrides)
5. FastAPI /approve endpoint and EventBus notification
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm_client import LocalLLMClient
from src.core.models import RiskLevel, Task, TaskStatus
from src.orchestrator.event_bus import EventBus
from src.orchestrator.workflow import UAOSWorkflow
from src.registry.tool_registry import ToolSpec
from src.workers.universal_worker import UniversalWorkerAgent


# ── 1. LLM Chat Stream Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_chat_stream():
    """Verify LocalLLMClient.chat_stream parses SSE chunk deltas correctly."""
    client = LocalLLMClient(base_url="http://localhost:1234/v1", model="test-model")

    mock_lines = [
        "data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}\n",
        "\n",
        "data: {\"choices\": [{\"delta\": {\"content\": \" World!\"}}]}\n",
        "\n",
        "data: [DONE]\n",
        "\n",
    ]

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            for line in mock_lines:
                yield line

    class FakeStreamContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("httpx.AsyncClient.stream", return_value=FakeStreamContext()):
        tokens = []
        async for token in client.chat_stream([{"role": "user", "content": "Hi"}]):
            tokens.append(token)

        assert tokens == ["Hello", " World!"]


# ── 2. EventBus Pub/Sub & Circular Buffer Tests ─────────────────────────


@pytest.mark.asyncio
async def test_event_bus_pub_sub_and_replay():
    """Verify EventBus broadcasting and ring-buffer replay to new subscribers."""
    bus = EventBus(max_history=10)
    wf_id = "wf-test-123"

    # 1. Publish 2 events prior to subscription
    bus.publish(wf_id, {"type": "token", "content": "Token 1"})
    bus.publish(wf_id, {"type": "token", "content": "Token 2"})

    # 2. Subscribe after publishing - should receive past events via replay
    received = []

    async def reader():
        async for ev in bus.subscribe(wf_id):
            received.append(ev)
            if len(received) == 3:
                break

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.01)

    # 3. Publish third event live
    bus.publish(wf_id, {"type": "token", "content": "Token 3"})

    await asyncio.wait_for(task, timeout=2.0)

    assert len(received) == 3
    assert received[0]["content"] == "Token 1"
    assert received[1]["content"] == "Token 2"
    assert received[2]["content"] == "Token 3"

    # 4. Cleanup
    bus.clear(wf_id)
    assert wf_id not in bus._history


# ── 3. UniversalWorkerAgent Streaming Callbacks Tests ─────────────────


@pytest.mark.asyncio
async def test_universal_worker_streaming():
    """Verify UniversalWorkerAgent fires on_token and on_event callbacks during ReAct loop."""
    mock_llm = AsyncMock(spec=LocalLLMClient)

    # When tools are present, the worker uses non-streaming chat() so the LLM
    # receives the OpenAI function-calling schema. Mock chat() accordingly.
    mock_llm.chat.side_effect = [
        # Step 1: LLM returns a tool call
        '{"tool": "add", "args": {"a": 2, "b": 3}}',
        # Step 2: LLM returns final answer after observing tool result
        "FINAL_ANSWER: 5",
    ]

    async def fake_add(a: int, b: int) -> int:
        return a + b

    tool = ToolSpec(
        tool_id="math_add",
        name="add",
        description="Add two numbers",
        skills_provided=["math"],
        parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
        risk_level=RiskLevel.LOW,
        function=fake_add,
    )

    task = Task(
        id="t-stream",
        name="Stream Task",
        description="Add 2 and 3",
        expected_output="Sum of numbers",
        required_skills=["math"],
        timeout_seconds=10,
    )

    received_tokens = []
    received_events = []

    def on_token(token: str):
        received_tokens.append(token)

    def on_event(event_dict: dict):
        received_events.append(event_dict)

    worker = UniversalWorkerAgent(llm=mock_llm)
    result = await worker.execute(
        task=task,
        persona="You are a helpful math solver.",
        tools=[tool],
        on_token=on_token,
        on_event=on_event,
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.output.strip() == "5"

    # Verify on_token was called with each non-streaming response
    assert len(received_tokens) > 0
    full_text = "".join(received_tokens)
    assert "FINAL_ANSWER: 5" in full_text

    # Verify tool events were triggered
    event_types = [ev["type"] for ev in received_events]
    assert "tool_start" in event_types
    assert "tool_end" in event_types
    assert "final_answer" in event_types


# ── 4. Workflow Interactive HITL Signal & Guidance Tests ──────────────


@pytest.mark.asyncio
async def test_workflow_interactive_hitl_signals():
    """Verify UAOSWorkflow correctly parses structured approval signal with guidance and params."""
    wf = UAOSWorkflow()

    # Initial state
    status = wf.get_status()
    assert status["awaiting_approval"] is False
    assert status["pending_task"] == ""
    assert status["pending_task_desc"] == ""
    assert status["pending_task_risk"] == ""
    assert status["pending_task_params"] == {}

    # Simulate pending high-risk task
    wf._pending_task_name = "Deploy Database Migration"
    wf._pending_task_id = "t-mig"
    wf._pending_task_desc = "Apply schema update to production db"
    wf._pending_task_risk = "critical"
    wf._pending_task_params = {"dry_run": False, "target": "prod"}

    status_pending = wf.get_status()
    assert status_pending["awaiting_approval"] is True
    assert status_pending["pending_task"] == "Deploy Database Migration"
    assert status_pending["pending_task_desc"] == "Apply schema update to production db"
    assert status_pending["pending_task_risk"] == "critical"
    assert status_pending["pending_task_params"] == {"dry_run": False, "target": "prod"}

    # Send structured approval signal with operator guidance and modified params
    signal_payload = {
        "approved": True,
        "guidance": "Please run in dry-run mode first, do not drop tables.",
        "modified_params": {"dry_run": True, "target": "staging"},
    }
    await wf.approve_task(signal_payload)

    assert wf._approval_result is True
    assert wf._approval_guidance == "Please run in dry-run mode first, do not drop tables."
    assert wf._approval_modified_params == {"dry_run": True, "target": "staging"}


@pytest.mark.asyncio
async def test_workflow_legacy_boolean_approval_signal():
    """Verify UAOSWorkflow maintains backwards compatibility with raw boolean approval signals."""
    wf = UAOSWorkflow()
    wf._pending_task_name = "Task 1"

    await wf.approve_task(True)
    assert wf._approval_result is True
    assert wf._approval_guidance == ""
    assert wf._approval_modified_params == {}

    await wf.approve_task(False)
    assert wf._approval_result is False


# ── 5. FastAPI /approve Endpoint Integration Test ──────────────────────


@pytest.mark.asyncio
async def test_api_approve_endpoint_with_guidance():
    """Verify POST /approve/{workflow_id} passes structured payload to Temporal and broadcasts to EventBus."""
    from httpx import ASGITransport, AsyncClient

    from src.api.main import app
    from src.orchestrator.event_bus import get_event_bus

    mock_temporal = MagicMock()
    mock_handle = AsyncMock()
    mock_temporal.get_workflow_handle.return_value = mock_handle
    app.state.temporal = mock_temporal

    wf_id = "wf-approval-test"
    bus = get_event_bus()

    # Pre-subscribe to verify EventBus receives approval_resolved
    received_bus_events = []

    async def bus_listener():
        async for ev in bus.subscribe(wf_id):
            received_bus_events.append(ev)
            if ev.get("type") == "approval_resolved":
                break

    listener_task = asyncio.create_task(bus_listener())
    await asyncio.sleep(0.01)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        res = await ac.post(
            f"/approve/{wf_id}",
            json={
                "approved": True,
                "guidance": "Approved with strict sandbox constraints",
                "modified_params": {"max_retries": 1},
            },
        )
        assert res.status_code == 200
        assert res.json()["action"] == "APPROVED"
        assert res.json()["guidance_provided"] is True

    # Check temporal signal call
    mock_handle.signal.assert_called_once_with(
        UAOSWorkflow.approve_task,
        {
            "approved": True,
            "guidance": "Approved with strict sandbox constraints",
            "modified_params": {"max_retries": 1},
        },
    )

    await asyncio.wait_for(listener_task, timeout=2.0)
    assert len(received_bus_events) > 0
    resolved_ev = next(e for e in received_bus_events if e.get("type") == "approval_resolved")
    assert resolved_ev["approved"] is True
    assert resolved_ev["guidance"] == "Approved with strict sandbox constraints"


@pytest.mark.asyncio
async def test_api_approve_endpoint_direct_mode():
    """Verify POST /approve/{workflow_id} in direct standalone mode resolves approval_event and publishes to bus."""
    from httpx import ASGITransport, AsyncClient

    from src.api.main import app
    from src.orchestrator.event_bus import get_event_bus

    app.state.temporal = None
    app.state.direct_workflows = {}

    wf_id = "wf-direct-approval-test"
    ev = asyncio.Event()
    app.state.direct_workflows[wf_id] = {
        "workflow_id": wf_id,
        "awaiting_approval": True,
        "approval_event": ev,
        "approval_response": None,
    }

    bus = get_event_bus()
    received_bus_events = []

    async def bus_listener():
        async for item in bus.subscribe(wf_id):
            received_bus_events.append(item)
            if item.get("type") == "approval_resolved":
                break

    listener_task = asyncio.create_task(bus_listener())
    await asyncio.sleep(0.01)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        res = await ac.post(
            f"/approve/{wf_id}",
            json={
                "approved": True,
                "guidance": "Standalone approval granted",
                "modified_params": {"safe_mode": True},
            },
        )
        assert res.status_code == 200
        assert res.json()["action"] == "APPROVED"
        assert res.json()["guidance_provided"] is True

    assert ev.is_set()
    dw = app.state.direct_workflows[wf_id]
    assert dw["approval_response"]["approved"] is True
    assert dw["approval_response"]["guidance"] == "Standalone approval granted"

    await asyncio.wait_for(listener_task, timeout=2.0)
    assert any(e.get("type") == "approval_resolved" and e.get("approved") is True for e in received_bus_events)


@pytest.mark.asyncio
async def test_api_status_endpoint_direct_mode():
    """Verify GET /status/{workflow_id} retrieves status from direct_workflows when Temporal is offline."""
    from httpx import ASGITransport, AsyncClient
    from src.api.main import app

    app.state.temporal = None
    wf_id = "wf-direct-status-test"
    app.state.direct_workflows[wf_id] = {
        "workflow_id": wf_id,
        "status": "completed",
        "awaiting_approval": False,
        "pending_task": "",
        "pending_task_id": "",
        "pending_task_desc": "",
        "pending_task_risk": "",
        "pending_task_params": {},
        "dag": {"tasks": []},
        "task_statuses": {"t1": "completed"},
        "supervisor_evaluations": [],
        "result": {"response": "All tasks done!"},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        res = await ac.get(f"/status/{wf_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["workflow_id"] == wf_id
        assert data["status"] == "completed"
        assert data["result"]["response"] == "All tasks done!"

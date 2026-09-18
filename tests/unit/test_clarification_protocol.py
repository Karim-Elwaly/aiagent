"""
Unit tests for the Interactive Clarification Protocol (Mid-Workflow Operator Dialogue).

Verifies:
- ClarificationHub lifecycle: request, wait, resolve, and timeout
- clarify_question tool execution within an agent task
- API endpoint POST /clarify/{workflow_id}
- GET /status/{workflow_id} reporting awaiting_clarification status
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from src.api.main import app
from src.core.clarification import (
    ClarificationHub,
    get_clarification_hub,
    current_workflow_id,
    current_task_id,
)
from src.orchestrator.event_bus import get_event_bus
from src.registry.tools.hermes_tools import clarify_question, CLARIFY_QUESTION_SPEC


@pytest.fixture(autouse=True)
def cleanup_clarification_hub():
    """Ensure clarification hub is reset before and after each test."""
    hub = get_clarification_hub()
    hub.reset()
    yield
    hub.reset()


@pytest.mark.asyncio
async def test_clarification_hub_request_and_resolve():
    """Verify that request_clarification pauses until resolve_clarification is called."""
    hub = get_clarification_hub()
    bus = get_event_bus()

    events_received = []
    wf_id = "wf-test-clarify-1"

    async def listener():
        async for ev in bus.subscribe(wf_id):
            events_received.append(ev)
            if ev.get("type") == "clarification_required":
                # Simulate operator answering via resolve
                cid = ev.get("clarification_id")
                hub.resolve_clarification(
                    workflow_id=wf_id,
                    answer="Option B: Use Staging Database",
                    clarification_id=cid,
                )
                break

    listen_task = asyncio.create_task(listener())

    # Small delay to ensure subscriber is listening
    await asyncio.sleep(0.05)

    result = await hub.request_clarification(
        question="Which database environment should be targeted?",
        choices=["Option A: Production DB", "Option B: Use Staging Database", "Option C: SQLite"],
        workflow_id=wf_id,
        task_id="t-db-mig",
        timeout_seconds=5,
    )

    await listen_task

    assert "Operator clarified: 'Option B: Use Staging Database'" in result
    assert any(ev.get("type") == "clarification_required" for ev in events_received)
    assert any(ev.get("type") == "clarification_resolved" for ev in events_received)


@pytest.mark.asyncio
async def test_clarification_hub_timeout_fallback():
    """Verify that an unanswered clarification cleanly times out and returns a default notice."""
    hub = get_clarification_hub()
    wf_id = "wf-test-timeout"

    result = await hub.request_clarification(
        question="Which log format do you prefer?",
        choices=["JSON (Recommended)", "Plain Text"],
        workflow_id=wf_id,
        task_id="t-logs",
        timeout_seconds=1,  # Short 1s timeout
    )

    assert "timed out after 1s" in result
    assert "JSON (Recommended)" in result


@pytest.mark.asyncio
async def test_clarify_question_tool_invocation():
    """Verify the clarify_question tool resolves contextvars and returns the answer."""
    hub = get_clarification_hub()
    wf_id = "wf-context-test"
    current_workflow_id.set(wf_id)
    current_task_id.set("t-deploy")

    async def auto_respond():
        await asyncio.sleep(0.1)
        pending = hub.get_pending(wf_id)
        assert pending is not None
        assert pending.task_id == "t-deploy"
        hub.resolve_clarification(
            workflow_id=wf_id,
            answer="Deploy to Staging first",
            clarification_id=pending.id,
        )

    respond_task = asyncio.create_task(auto_respond())

    answer = await clarify_question(
        question="Where should the service be deployed?",
        choices=["Production", "Staging first"],
    )

    await respond_task
    assert "Operator clarified: 'Deploy to Staging first'" in answer
    assert CLARIFY_QUESTION_SPEC.name == "clarify_question"


@pytest.mark.asyncio
async def test_api_clarify_endpoint_and_status():
    """Verify POST /clarify/{workflow_id} and GET /status/{workflow_id} integration."""
    hub = get_clarification_hub()
    wf_id = "wf-api-test-123"

    # Simulate a direct workflow in app.state
    app.state.direct_workflows[wf_id] = {
        "status": "running",
        "pending_task": "Analyze Performance",
        "pending_task_id": "t-perf",
        "dag": None,
        "task_statuses": {"t-perf": "running"},
    }

    # Start an asynchronous clarification request
    clarify_task = asyncio.create_task(
        hub.request_clarification(
            question="Include memory profiling in benchmark?",
            choices=["Yes, include memory profiling", "No, CPU metrics only"],
            workflow_id=wf_id,
            task_id="t-perf",
            timeout_seconds=10,
        )
    )

    await asyncio.sleep(0.05)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Verify GET /status reports awaiting_clarification = True
        status_res = await client.get(f"/status/{wf_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["awaiting_clarification"] is True
        assert status_data["clarification_request"]["question"] == "Include memory profiling in benchmark?"
        assert len(status_data["clarification_request"]["choices"]) == 2

        # 2. Submit clarification via POST /clarify/{workflow_id}
        clarify_res = await client.post(
            f"/clarify/{wf_id}",
            json={
                "answer": "Yes, include memory profiling",
                "clarification_id": status_data["clarification_request"]["id"],
            },
        )
        assert clarify_res.status_code == 200
        assert clarify_res.json()["status"] == "ok"
        assert clarify_res.json()["resolved"] is True

        # 3. Verify tool returned the submitted answer
        tool_result = await clarify_task
        assert "Operator clarified: 'Yes, include memory profiling'" in tool_result

        # 4. Verify status now reports awaiting_clarification = False
        status_res2 = await client.get(f"/status/{wf_id}")
        assert status_res2.status_code == 200
        assert status_res2.json()["awaiting_clarification"] is False

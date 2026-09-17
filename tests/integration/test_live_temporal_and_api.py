"""
Live verification tests:
1. Connecting to running Temporal server (localhost:7233)
2. Verifying Worker registration with UAOSWorkflow and all activities
3. FastAPI endpoint verification (/health, /tools)
"""

import pytest
from fastapi.testclient import TestClient
from temporalio.client import Client
from temporalio.worker import Worker

from src.api.main import app
from src.orchestrator.activities import (
    assemble_response,
    execute_task,
    plan_tasks,
    replan_tasks,
)
from src.orchestrator.workflow import UAOSWorkflow


@pytest.mark.asyncio
async def test_live_temporal_connection_and_worker():
    """Verify live connection to Temporal and worker registration."""
    try:
        client = await Client.connect("localhost:7233", namespace="default")
    except Exception as e:
        pytest.skip(f"Temporal server not running locally: {e}")

    assert client.namespace == "default"

    # Verify worker initialization and workflow sandbox validation
    worker = Worker(
        client,
        task_queue="uaos-test-queue",
        workflows=[UAOSWorkflow],
        activities=[
            plan_tasks,
            execute_task,
            replan_tasks,
            assemble_response,
        ],
    )
    assert worker is not None


def test_api_tools_endpoint():
    """Verify FastAPI /tools endpoint returns all auto-discovered tools."""
    with TestClient(app) as test_client:
        response = test_client.get("/tools")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        tool_names = [t["name"] for t in data]
        assert "read_file" in tool_names
        assert "execute_python" in tool_names
        assert "web_search" in tool_names


def test_api_health_endpoint():
    """Verify FastAPI /health endpoint."""
    with TestClient(app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "temporal_available" in data
        assert "llm_available" in data
        assert "tools_registered" in data
        assert data["tools_registered"] >= 6


def test_api_serves_modern_ui():
    """Verify FastAPI root endpoint serves the modern web UI."""
    with TestClient(app) as test_client:
        response = test_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "UAOS" in response.text
        assert "Universal Agent Orchestration" in response.text
        assert "Workflow Execution Plan" in response.text
        assert "LLM Settings" in response.text
        assert "Agent Studio" in response.text


def test_llm_settings_endpoints():
    """Verify runtime LLM configuration GET, POST, and test-llm endpoints."""
    with TestClient(app) as test_client:
        # 1. Get current LLM settings
        get_res = test_client.get("/api/settings/llm")
        assert get_res.status_code == 200
        data = get_res.json()
        assert "base_url" in data
        assert "model" in data

        # 2. Update LLM settings dynamically (e.g. LM Studio on a VM IP)
        update_res = test_client.post(
            "/api/settings/llm",
            json={
                "base_url": "http://192.168.1.100:1234/v1",
                "model": "qwen2.5-7b-instruct",
                "temperature": 0.2,
                "max_tokens": 4096,
            },
        )
        assert update_res.status_code == 200
        assert update_res.json()["status"] == "updated"

        # Verify updated settings reflected
        get_res2 = test_client.get("/api/settings/llm")
        assert get_res2.json()["base_url"] == "http://192.168.1.100:1234/v1"
        assert get_res2.json()["model"] == "qwen2.5-7b-instruct"

        # 3. Test LLM connection endpoint
        test_res = test_client.post(
            "/api/settings/test-llm",
            json={"base_url": "http://127.0.0.1:59999/v1", "model": "test"},
        )
        assert test_res.status_code == 200
        assert test_res.json()["connected"] is False

        # 4. Restore original settings
        test_client.post("/api/settings/llm", json=data)




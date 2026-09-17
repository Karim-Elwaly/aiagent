"""
UAOS API — FastAPI Gateway

Provides HTTP endpoints for submitting problems, checking status,
and approving high-risk tasks.

Endpoints:
  POST /solve           — Submit a problem, wait for result
  POST /solve/async     — Submit a problem, return immediately
  GET  /status/{id}     — Check workflow status
  POST /approve/{id}    — Approve/reject a high-risk task
  GET  /health          — Health check (LLM + Temporal connectivity)
  GET  /tools           — List all registered tools and skills
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from temporalio.client import Client

from src.core.config import get_settings
from src.core.llm_client import LocalLLMClient
from src.orchestrator.event_bus import get_event_bus
from src.brain.skill_builder import SkillBuilder
from src.core.agent_models import (
    AgentCreateRequest,
    AgentGenerateRequest,
    AgentGenerateResponse,
    AgentProfile,
    AgentUpdateRequest,
    SkillGenerateRequest,
    SkillGenerateResponse,
    SkillRegisterRequest,
)
from src.core.agent_store import AgentStore
from src.orchestrator.workflow import UAOSWorkflow
from src.registry.auto_discover import register_all_tools
from src.registry.mcp.mcp_adapter import mcp_tool_to_tool_spec
from src.registry.mcp.mcp_client import MCPClient
from src.registry.openapi.openapi_parser import parse_openapi_spec
from src.registry.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ── Request/Response Models ──────────────────────────────────────


class SolveRequest(BaseModel):
    query: str
    agent_id: str | None = None


class SolveAsyncResponse(BaseModel):
    workflow_id: str
    status: str = "running"


class SolveResponse(BaseModel):
    workflow_id: str
    response: str
    tasks_completed: int
    tasks_failed: int
    replans: int


class ApproveRequest(BaseModel):
    approved: bool
    guidance: str | None = None
    modified_params: dict[str, Any] | None = None


class StatusResponse(BaseModel):
    workflow_id: str
    status: str
    awaiting_approval: bool = False
    pending_task: str = ""
    pending_task_id: str = ""
    pending_task_desc: str = ""
    pending_task_risk: str = ""
    pending_task_params: dict[str, Any] = {}
    dag: dict[str, Any] | None = None
    task_statuses: dict[str, str] = {}
    result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    llm_available: bool
    temporal_available: bool
    tools_registered: int
    skills_available: int


class ToolInfo(BaseModel):
    tool_id: str
    name: str
    description: str
    skills_provided: list[str]
    risk_level: str
    source_type: str = "native"
    server_or_host: str = ""


class MCPConnectPayload(BaseModel):
    server_id: str
    transport: str = "stdio"  # "stdio" | "sse"
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None


class MCPDisconnectPayload(BaseModel):
    server_id: str


class OpenAPIImportPayload(BaseModel):
    spec: str  # raw JSON/YAML string OR URL starting with http:// or https://
    base_url: str | None = None
    auth_header_name: str | None = None
    auth_header_value: str | None = None
    api_prefix: str = "api"


class LLMConfigPayload(BaseModel):
    base_url: str
    model: str
    temperature: float = 0.1
    max_tokens: int = 4096


class LLMTestPayload(BaseModel):
    base_url: str
    model: str | None = None



# ── Application Lifecycle ────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    settings = get_settings()

    # Initialize Tool Registry
    registry = ToolRegistry()
    register_all_tools(registry)
    app.state.registry = registry
    logger.info("Tool Registry: %s", registry)

    # Connect to Temporal
    try:
        app.state.temporal = await Client.connect(
            settings.temporal_host,
            namespace=settings.temporal_namespace,
        )
        logger.info("Connected to Temporal at %s", settings.temporal_host)
    except Exception as e:
        logger.error("Failed to connect to Temporal: %s", e)
        app.state.temporal = None

    # Initialize LLM client (for health check)
    app.state.llm = LocalLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )

    # Initialize active MCP clients dictionary
    app.state.mcp_clients: dict[str, MCPClient] = {}

    app.state.settings = settings

    logger.info("UAOS API ready at http://%s:%d", settings.api_host, settings.api_port)

    yield

    # Shutdown: gracefully close any open MCP clients
    for s_id, mcp_client in list(app.state.mcp_clients.items()):
        try:
            await mcp_client.close()
            logger.info("Closed MCP client '%s'", s_id)
        except Exception as e:
            logger.warning("Error closing MCP client '%s': %s", s_id, e)

    logger.info("UAOS API shutting down")


# ── FastAPI App ──────────────────────────────────────────────────

app = FastAPI(
    title="UAOS — Universal Agent Orchestration System",
    description=(
        "A durable, self-hosted system that dynamically analyzes any problem, "
        "decomposes it into tasks, and spawns Universal Worker Agents to execute."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── UI Static Files Mount ─────────────────────────────────────────
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")
    css_dir = UI_DIR / "css"
    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    js_dir = UI_DIR / "js"
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")


@app.get("/", response_class=FileResponse)
async def serve_ui():
    """Serve the modern web UI mission control dashboard."""
    index_path = UI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "UAOS API Gateway", "docs": "/docs"}


# ── Endpoints ────────────────────────────────────────────────────


@app.post("/solve", response_model=SolveResponse)
async def solve(request: SolveRequest):
    """Submit a problem and wait for the complete result.

    The system will:
    1. Analyze the problem
    2. Decompose it into tasks
    3. Execute each task with a Universal Worker Agent
    4. Assemble and return the final response

    Note: This is a blocking call. For long-running tasks, use /solve/async.
    """
    if not app.state.temporal:
        raise HTTPException(503, "Temporal server not available")

    workflow_id = f"uaos-{uuid4().hex[:12]}"

    logger.info(
        "Solving (sync): workflow=%s, query=%s, agent_id=%s",
        workflow_id,
        request.query[:100],
        request.agent_id or "default",
    )

    try:
        handle = await app.state.temporal.start_workflow(
            UAOSWorkflow.run,
            request.query,
            request.agent_id or "",
            id=workflow_id,
            task_queue=app.state.settings.temporal_task_queue,
        )

        result = await handle.result()

        return SolveResponse(
            workflow_id=workflow_id,
            response=result.get("response", ""),
            tasks_completed=result.get("tasks_completed", 0),
            tasks_failed=result.get("tasks_failed", 0),
            replans=result.get("replans", 0),
        )

    except Exception as e:
        logger.exception("Workflow failed")
        raise HTTPException(500, f"Workflow execution failed: {e}")


@app.post("/solve/async", response_model=SolveAsyncResponse)
async def solve_async(request: SolveRequest):
    """Submit a problem and return immediately.

    Use GET /status/{workflow_id} to check progress.
    """
    if not app.state.temporal:
        raise HTTPException(503, "Temporal server not available")

    workflow_id = f"uaos-{uuid4().hex[:12]}"

    logger.info(
        "Solving (async): workflow=%s, query=%s, agent_id=%s",
        workflow_id,
        request.query[:100],
        request.agent_id or "default",
    )

    try:
        await app.state.temporal.start_workflow(
            UAOSWorkflow.run,
            request.query,
            request.agent_id or "",
            id=workflow_id,
            task_queue=app.state.settings.temporal_task_queue,
        )

        return SolveAsyncResponse(
            workflow_id=workflow_id,
            status="running",
        )

    except Exception as e:
        logger.error("Failed to start workflow: %s", e)
        raise HTTPException(500, f"Failed to start workflow: {e}")


@app.get("/status/{workflow_id}", response_model=StatusResponse)
async def get_status(workflow_id: str):
    """Check the status of a running workflow."""
    if not app.state.temporal:
        raise HTTPException(503, "Temporal server not available")

    try:
        handle = app.state.temporal.get_workflow_handle(workflow_id)
        desc = await handle.describe()

        query_res = {}
        try:
            query_res = await handle.query(UAOSWorkflow.get_status)
        except Exception as q_err:
            logger.debug("Query get_status returned exception: %s", q_err)

        result_data = query_res.get("result")
        if not result_data and desc.status.name.lower() == "completed":
            try:
                result_data = await handle.result()
            except Exception as r_err:
                logger.debug("Could not get handle.result(): %s", r_err)

        return StatusResponse(
            workflow_id=workflow_id,
            status=desc.status.name.lower(),
            awaiting_approval=query_res.get("awaiting_approval", False),
            pending_task=query_res.get("pending_task", ""),
            pending_task_id=query_res.get("pending_task_id", ""),
            pending_task_desc=query_res.get("pending_task_desc", ""),
            pending_task_risk=query_res.get("pending_task_risk", ""),
            pending_task_params=query_res.get("pending_task_params", {}),
            dag=query_res.get("dag"),
            task_statuses=query_res.get("task_statuses", {}),
            result=result_data,
        )

    except Exception as e:
        raise HTTPException(404, f"Workflow not found: {e}")


@app.post("/approve/{workflow_id}")
async def approve_task(workflow_id: str, request: ApproveRequest):
    """Approve or reject a high-risk task with optional operator guidance and parameter overrides.

    When a task with HIGH or CRITICAL risk level is encountered,
    the workflow pauses and waits for this signal.
    """
    if not app.state.temporal:
        raise HTTPException(503, "Temporal server not available")

    try:
        handle = app.state.temporal.get_workflow_handle(workflow_id)
        payload = {
            "approved": request.approved,
            "guidance": request.guidance or "",
            "modified_params": request.modified_params or {},
        }
        await handle.signal(UAOSWorkflow.approve_task, payload)

        action = "APPROVED" if request.approved else "REJECTED"
        logger.info(
            "Task %s for workflow %s (guidance: '%s')",
            action,
            workflow_id,
            request.guidance or "none",
        )

        # Notify event bus
        get_event_bus().publish(
            workflow_id,
            {
                "type": "approval_resolved",
                "approved": request.approved,
                "guidance": request.guidance,
            },
        )

        return {
            "workflow_id": workflow_id,
            "action": action,
            "guidance_provided": bool(request.guidance),
        }

    except Exception as e:
        raise HTTPException(404, f"Workflow not found: {e}")


@app.get("/stream/{workflow_id}")
async def stream_workflow_events(workflow_id: str):
    """Server-Sent Events (SSE) streaming endpoint for real-time tokens & workflow state."""
    bus = get_event_bus()

    async def event_generator():
        async for event in bus.subscribe(workflow_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """System health check."""
    llm_ok = await app.state.llm.health_check()

    temporal_ok = False
    if app.state.temporal:
        try:
            # Quick connectivity check
            await app.state.temporal.count_workflows()
            temporal_ok = True
        except Exception:
            temporal_ok = False

    registry: ToolRegistry = app.state.registry

    status = "healthy" if (llm_ok and temporal_ok) else "degraded"

    return HealthResponse(
        status=status,
        llm_available=llm_ok,
        temporal_available=temporal_ok,
        tools_registered=registry.tool_count,
        skills_available=registry.skill_count,
    )


@app.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """List all registered tools and their capabilities."""
    registry: ToolRegistry = app.state.registry

    return [
        ToolInfo(
            tool_id=t.tool_id,
            name=t.name,
            description=t.description,
            skills_provided=t.skills_provided,
            risk_level=t.risk_level.value,
            source_type=t.source_type,
            server_or_host=t.server_or_host,
        )
        for t in registry.get_all_tools()
    ]


@app.post("/api/tools/mcp/connect")
async def connect_mcp_server(payload: MCPConnectPayload):
    """Connect to a Model Context Protocol (MCP) server and register its tools."""
    registry: ToolRegistry = app.state.registry
    server_id = payload.server_id.strip()

    if not server_id:
        raise HTTPException(status_code=400, detail="server_id cannot be empty")

    # If already connected, close old client first
    if server_id in app.state.mcp_clients:
        old_client = app.state.mcp_clients[server_id]
        await old_client.close()
        registry.unregister_by_source(source_type="mcp", server_or_host=server_id)

    client = MCPClient(
        server_id=server_id,
        transport=payload.transport,
        command=payload.command,
        args=payload.args,
        env=payload.env,
        url=payload.url,
    )

    try:
        await client.connect()
        mcp_tools = await client.list_tools()
    except Exception as e:
        logger.error("Failed to connect to MCP server '%s': %s", server_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to connect to MCP server: {e}"
        ) from e

    app.state.mcp_clients[server_id] = client

    # Convert and register all tools
    registered_specs = []
    for tool_dict in mcp_tools:
        spec = mcp_tool_to_tool_spec(tool_dict, client, server_id)
        registry.register(spec)
        registered_specs.append(spec)

    return {
        "status": "connected",
        "server_id": server_id,
        "transport": payload.transport,
        "tools_count": len(registered_specs),
        "tools": [
            {
                "tool_id": s.tool_id,
                "name": s.name,
                "description": s.description,
                "skills": s.skills_provided,
                "risk_level": s.risk_level.value,
            }
            for s in registered_specs
        ],
    }


@app.get("/api/tools/mcp/servers")
async def list_mcp_servers():
    """List all currently connected MCP servers and their tools."""
    registry: ToolRegistry = app.state.registry
    servers_info = []

    for server_id, client in app.state.mcp_clients.items():
        server_tools = [
            t for t in registry.get_all_tools()
            if t.source_type == "mcp" and t.server_or_host == server_id
        ]
        servers_info.append({
            "server_id": server_id,
            "transport": client.transport,
            "connected": client.is_connected,
            "tools_count": len(server_tools),
            "tools": [t.name for t in server_tools],
        })

    return servers_info


@app.post("/api/tools/mcp/disconnect")
async def disconnect_mcp_server(payload: MCPDisconnectPayload):
    """Disconnect an MCP server and unregister all its tools."""
    registry: ToolRegistry = app.state.registry
    server_id = payload.server_id

    client = app.state.mcp_clients.pop(server_id, None)
    if client:
        await client.close()

    removed = registry.unregister_by_source(source_type="mcp", server_or_host=server_id)
    return {
        "status": "disconnected",
        "server_id": server_id,
        "removed_tools_count": len(removed),
        "removed_tools": removed,
    }


@app.post("/api/tools/openapi/import")
async def import_openapi_spec(payload: OpenAPIImportPayload):
    """Import an OpenAPI 3.0 / Swagger spec and register tools."""
    registry: ToolRegistry = app.state.registry
    spec_content = payload.spec.strip()

    # If spec is a URL, fetch it
    if spec_content.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=15.0) as http_client:
                resp = await http_client.get(spec_content)
                resp.raise_for_status()
                spec_content = resp.text
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to fetch OpenAPI spec from URL: {e}"
            ) from e

    try:
        tools = parse_openapi_spec(
            raw_spec=spec_content,
            base_url=payload.base_url,
            auth_header_name=payload.auth_header_name,
            auth_header_value=payload.auth_header_value,
            api_prefix=payload.api_prefix,
        )
    except Exception as e:
        logger.error("Failed to parse OpenAPI spec: %s", e)
        raise HTTPException(
            status_code=400, detail=f"Failed to parse OpenAPI spec: {e}"
        ) from e

    registry.register_batch(tools)

    return {
        "status": "imported",
        "tools_count": len(tools),
        "base_url": payload.base_url or (tools[0].server_or_host if tools else ""),
        "tools": [
            {
                "tool_id": t.tool_id,
                "name": t.name,
                "description": t.description,
                "skills": t.skills_provided,
                "risk_level": t.risk_level.value,
                "server_or_host": t.server_or_host,
            }
            for t in tools
        ],
    }


@app.delete("/api/tools/{tool_id}")
async def unregister_tool(tool_id: str):
    """Unregister a dynamic tool by ID."""
    registry: ToolRegistry = app.state.registry
    success = registry.unregister(tool_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
    return {"status": "unregistered", "tool_id": tool_id}


@app.get("/api/settings/llm")
async def get_llm_settings():
    """Return current LLM configuration."""
    settings = get_settings()
    return {
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }


@app.post("/api/settings/llm")
async def update_llm_settings(payload: LLMConfigPayload):
    """Update runtime LLM settings without restarting the server."""
    from src.core.config import save_runtime_settings

    updates = {
        "llm_base_url": payload.base_url.rstrip("/"),
        "llm_model": payload.model,
        "llm_temperature": payload.temperature,
        "llm_max_tokens": payload.max_tokens,
    }
    settings = save_runtime_settings(updates)

    # Update app state LLM client
    app.state.llm = LocalLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )

    # Reset worker activities LLM singletons so changes take effect immediately
    from src.orchestrator.activities import reset_llm_clients

    reset_llm_clients()

    return {"status": "updated", "config": payload.model_dump()}


@app.post("/api/settings/test-llm")
async def test_llm_connection(payload: LLMTestPayload):
    """Test connection to an LLM endpoint (e.g. LM Studio on a VM)."""
    base_url = payload.base_url.rstrip("/")
    client = LocalLLMClient(base_url=base_url, model=payload.model or "default")
    is_healthy = await client.health_check()
    models = await client.list_models()

    return {
        "connected": is_healthy or len(models) > 0,
        "models": models,
        "base_url": base_url,
        "model_tested": payload.model,
    }


# ── Agent Management Endpoints ────────────────────────────────────


@app.get("/api/agents", response_model=list[AgentProfile])
async def list_agents():
    """List all saved reusable agent profiles."""
    store = AgentStore()
    return store.list_all()


@app.post("/api/agents", response_model=AgentProfile)
async def create_agent(payload: AgentCreateRequest):
    """Create and persist a new reusable agent profile."""
    store = AgentStore()
    agent_id = store.generate_id(payload.name)

    # Ensure unique ID if name collision
    existing = store.load(agent_id)
    if existing:
        agent_id = f"{agent_id}-{uuid4().hex[:4]}"

    profile = AgentProfile(
        id=agent_id,
        name=payload.name,
        description=payload.description,
        icon=payload.icon or "🤖",
        system_prompt_template=payload.system_prompt_template,
        curated_skills=payload.curated_skills,
        tags=payload.tags,
    )
    store.save(profile)
    return profile


@app.get("/api/agents/{agent_id}", response_model=AgentProfile)
async def get_agent(agent_id: str):
    """Get details of a specific agent profile."""
    store = AgentStore()
    profile = store.load(agent_id)
    if not profile:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return profile


@app.put("/api/agents/{agent_id}", response_model=AgentProfile)
async def update_agent(agent_id: str, payload: AgentUpdateRequest):
    """Update an existing agent profile."""
    store = AgentStore()
    profile = store.load(agent_id)
    if not profile:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    if payload.name is not None:
        profile.name = payload.name
    if payload.description is not None:
        profile.description = payload.description
    if payload.icon is not None:
        profile.icon = payload.icon
    if payload.system_prompt_template is not None:
        profile.system_prompt_template = payload.system_prompt_template
    if payload.curated_skills is not None:
        profile.curated_skills = payload.curated_skills
    if payload.tags is not None:
        profile.tags = payload.tags

    store.save(profile)
    return profile


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete a saved agent profile."""
    store = AgentStore()
    deleted = store.delete(agent_id)
    if not deleted:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return {"status": "deleted", "agent_id": agent_id}


@app.post("/api/agents/generate", response_model=AgentGenerateResponse)
async def generate_agent(payload: AgentGenerateRequest):
    """Use LLM to generate an optimized agent configuration from natural language."""
    registry: ToolRegistry = app.state.registry
    skills = registry.list_skills()
    builder = SkillBuilder(llm=app.state.llm)
    return await builder.generate_agent_profile(
        payload.description, available_skills=skills
    )


# ── AI Skill Builder Endpoints ───────────────────────────────────


@app.post("/api/skills/generate", response_model=SkillGenerateResponse)
async def generate_skill(payload: SkillGenerateRequest):
    """Use LLM to generate Python tool code from natural language description."""
    registry: ToolRegistry = app.state.registry
    skills = registry.list_skills()
    builder = SkillBuilder(llm=app.state.llm)
    return await builder.generate_tool(
        description=payload.description,
        suggested_name=payload.suggested_name,
        available_skills=skills,
    )


@app.post("/api/skills/register")
async def register_skill(payload: SkillRegisterRequest):
    """Validate, register and persist a generated custom Python tool."""
    registry: ToolRegistry = app.state.registry
    builder = SkillBuilder(llm=app.state.llm)
    try:
        tool_spec = builder.register_generated_tool(
            tool_code=payload.tool_code,
            tool_name=payload.tool_name,
            registry=registry,
            persist=True,
        )
        return {
            "status": "registered",
            "tool_id": tool_spec.tool_id,
            "name": tool_spec.name,
            "description": tool_spec.description,
            "skills": tool_spec.skills_provided,
            "risk_level": tool_spec.risk_level.value,
        }
    except Exception as e:
        logger.exception("Failed to register generated skill")
        raise HTTPException(400, f"Failed to register skill: {e}")


# ── Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )

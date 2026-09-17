"""Integration tests for dynamic tool registration (MCP and OpenAPI)."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.api.main import app
from src.registry.mcp.mcp_adapter import mcp_tool_to_tool_spec
from src.registry.mcp.mcp_client import MCPClient
from src.registry.openapi.openapi_parser import parse_openapi_spec
from src.registry.tool_registry import ToolRegistry

SAMPLE_SPEC_JSON = """
{
  "openapi": "3.0.0",
  "info": {"title": "Test API", "version": "1.0"},
  "servers": [{"url": "https://api.test.com"}],
  "paths": {
    "/items": {
      "get": {
        "operationId": "getItems",
        "summary": "Retrieve all items",
        "tags": ["inventory"]
      }
    }
  }
}
"""


def test_registry_dynamic_batch_and_unregistration():
    registry = ToolRegistry()
    initial_skills = registry.list_skills()
    assert len(initial_skills) == 0

    # 1. Parse and register OpenAPI tools
    openapi_tools = parse_openapi_spec(SAMPLE_SPEC_JSON, api_prefix="inv")
    count = registry.register_batch(openapi_tools)
    assert count == 1
    assert "inventory" in registry.list_skills()
    assert registry.tool_count == 1

    # 2. Add an MCP tool
    mock_mcp = AsyncMock(spec=MCPClient)
    mcp_tool_raw = {
        "name": "sql_query",
        "description": "Run SQL",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
    }
    mcp_spec = mcp_tool_to_tool_spec(mcp_tool_raw, mock_mcp, server_id="dw")
    registry.register(mcp_spec)

    assert registry.tool_count == 2
    assert "dw" in registry.list_skills()
    assert "inventory" in registry.list_skills()

    # 3. Resolve skills to concrete tools
    resolved = registry.resolve(["inventory", "dw"])
    assert len(resolved) == 2
    names = {t.name for t in resolved}
    assert "inv_getitems" in names
    assert "sql_query" in names

    # 4. Filter by source
    openapi_registered = registry.get_tools_by_source("openapi")
    assert len(openapi_registered) == 1
    assert openapi_registered[0].source_type == "openapi"

    mcp_registered = registry.get_tools_by_source("mcp")
    assert len(mcp_registered) == 1
    assert mcp_registered[0].source_type == "mcp"

    # 5. Clean up OpenAPI tools
    removed = registry.unregister_by_source("openapi")
    assert len(removed) == 1
    assert registry.tool_count == 1
    assert "inventory" not in registry.list_skills()
    assert "dw" in registry.list_skills()


def test_api_openapi_import_and_tool_lifecycle():
    with TestClient(app) as client:
        # 1. Import OpenAPI Spec
        resp = client.post(
            "/api/tools/openapi/import",
            json={
                "spec": SAMPLE_SPEC_JSON,
                "base_url": "https://api.test.com",
                "api_prefix": "live_test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "imported"
        assert data["tools_count"] == 1
        tool_id = data["tools"][0]["tool_id"]

        # 2. Verify in /tools
        tools_resp = client.get("/tools")
        assert tools_resp.status_code == 200
        all_tools = tools_resp.json()
        imported = [t for t in all_tools if t["tool_id"] == tool_id]
        assert len(imported) == 1
        assert imported[0]["source_type"] == "openapi"
        assert imported[0]["server_or_host"] == "https://api.test.com"

        # 3. Delete imported tool
        del_resp = client.delete(f"/api/tools/{tool_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "unregistered"

        # 4. Verify removal
        tools_after = client.get("/tools").json()
        assert not any(t["tool_id"] == tool_id for t in tools_after)

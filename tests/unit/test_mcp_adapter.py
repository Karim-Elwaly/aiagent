"""Unit tests for Model Context Protocol (MCP) Adapter."""

from unittest.mock import AsyncMock

import pytest

from src.core.models import RiskLevel
from src.registry.mcp.mcp_adapter import (
    convert_mcp_schema_to_parameters,
    derive_skills_from_tool,
    determine_risk_level,
    mcp_tool_to_tool_spec,
)
from src.registry.mcp.mcp_client import MCPClient


def test_derive_skills_from_tool():
    skills = derive_skills_from_tool(
        name="create_issue",
        description="Create a new GitHub issue with title and body",
        server_id="github",
    )
    assert "github" in skills
    assert "create_issue" in skills
    assert "create" in skills
    assert "issue" in skills
    assert "github_create_issue" in skills


def test_determine_risk_level():
    assert determine_risk_level("get_user", "Fetch user profile") == RiskLevel.LOW
    assert determine_risk_level("create_repo", "Create a new repository") == RiskLevel.HIGH
    assert determine_risk_level("delete_database", "Drop database permanently") == RiskLevel.CRITICAL
    assert determine_risk_level("terminate_process", "Kill running process") == RiskLevel.CRITICAL


def test_convert_mcp_schema_to_parameters():
    mcp_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SQL query to execute"},
            "limit": {"type": "integer", "description": "Max rows"},
        },
        "required": ["query"],
    }
    params = convert_mcp_schema_to_parameters(mcp_schema)
    assert "query" in params
    assert params["query"]["type"] == "string"
    assert params["query"]["required"] is True
    assert "limit" in params
    assert params["limit"]["type"] == "integer"
    assert params["limit"]["required"] is False


@pytest.mark.asyncio
async def test_mcp_tool_to_tool_spec_and_execution():
    mock_client = AsyncMock(spec=MCPClient)
    mock_client.call_tool.return_value = "Query executed: 42 rows"

    mcp_tool = {
        "name": "query_database",
        "description": "Execute a readonly SQL query",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The SQL query"}
            },
            "required": ["sql"],
        },
    }

    spec = mcp_tool_to_tool_spec(mcp_tool, mock_client, server_id="postgres")

    assert spec.tool_id == "mcp_postgres_query_database"
    assert spec.name == "query_database"
    assert spec.source_type == "mcp"
    assert spec.server_or_host == "postgres"
    assert spec.risk_level == RiskLevel.LOW
    assert "postgres" in spec.skills_provided
    assert "query" in spec.skills_provided

    # Execute the callable
    output = await spec.function(sql="SELECT * FROM users")
    assert output == "Query executed: 42 rows"
    mock_client.call_tool.assert_called_once_with("query_database", {"sql": "SELECT * FROM users"})

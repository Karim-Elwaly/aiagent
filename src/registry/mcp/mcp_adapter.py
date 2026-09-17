"""Model Context Protocol (MCP) Adapter.

Converts MCP tool definitions into UAOS ToolSpec instances, mapping:
  - Input JSON Schemas → UAOS parameter dictionaries
  - Tool names/descriptions → Abstract skills for Meta-Planner
  - Mutating operations → Risk levels (LOW, HIGH, CRITICAL)
"""

from __future__ import annotations

import re
from typing import Any

from src.core.models import RiskLevel
from src.registry.mcp.mcp_client import MCPClient
from src.registry.tool_registry import ToolSpec

CRITICAL_KEYWORDS = {
    "delete", "drop", "destroy", "kill", "rm", "remove", "truncate", "purge", "revoke", "terminate"
}
HIGH_KEYWORDS = {
    "create", "write", "update", "modify", "patch", "post", "put", "insert", "execute", "run", "send", "commit", "push"
}


def derive_skills_from_tool(name: str, description: str, server_id: str) -> list[str]:
    """Derive abstract skill names for the Meta-Planner from tool metadata."""
    skills = set()

    # 1. Server-level skill
    clean_server = re.sub(r"[^a-zA-Z0-9_]", "_", server_id.lower()).strip("_")
    if clean_server:
        skills.add(clean_server)

    # 2. Tool name as a skill
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()).strip("_")
    if clean_name:
        skills.add(clean_name)
        skills.add(f"{clean_server}_{clean_name}")

    # 3. Word tokens from tool name (e.g., 'create_issue' -> 'create', 'issue')
    for token in clean_name.split("_"):
        if len(token) > 2 and token not in ("the", "and", "for", "with", "from"):
            skills.add(token)

    return sorted(skills)


def determine_risk_level(name: str, description: str) -> RiskLevel:
    """Determine risk level based on tool name and description semantics."""
    text = f"{name} {description}".lower()
    tokens = set(re.findall(r"\b\w+\b", text))

    if tokens & CRITICAL_KEYWORDS:
        return RiskLevel.CRITICAL
    if tokens & HIGH_KEYWORDS:
        return RiskLevel.HIGH
    return RiskLevel.LOW


def convert_mcp_schema_to_parameters(input_schema: dict[str, Any] | None) -> dict[str, Any]:
    """Convert MCP JSON Schema object to UAOS parameters specification."""
    if not input_schema or not isinstance(input_schema, dict):
        return {}

    properties = input_schema.get("properties", {})
    required_fields = set(input_schema.get("required", []))

    parameters: dict[str, Any] = {}
    for param_name, schema in properties.items():
        if not isinstance(schema, dict):
            continue

        p_type = schema.get("type", "string")
        p_desc = schema.get("description", "")
        p_req = param_name in required_fields

        parameters[param_name] = {
            "type": p_type,
            "description": p_desc,
            "required": p_req,
        }

    return parameters


def mcp_tool_to_tool_spec(
    mcp_tool: dict[str, Any], client: MCPClient, server_id: str
) -> ToolSpec:
    """Convert an MCP tool definition into a registered UAOS ToolSpec."""
    tool_name = mcp_tool.get("name", "unnamed_tool")
    description = mcp_tool.get("description", f"MCP tool from server '{server_id}'")
    input_schema = mcp_tool.get("inputSchema", {})

    tool_id = f"mcp_{server_id}_{tool_name}"
    parameters = convert_mcp_schema_to_parameters(input_schema)
    skills = derive_skills_from_tool(tool_name, description, server_id)
    risk_level = determine_risk_level(tool_name, description)

    # Dynamic async wrapper function that delegates to client.call_tool
    async def call_mcp_tool(**kwargs: Any) -> str:
        return await client.call_tool(tool_name, kwargs)

    # Set function name for clear logging/stack traces
    call_mcp_tool.__name__ = tool_name
    call_mcp_tool.__doc__ = description

    return ToolSpec(
        tool_id=tool_id,
        name=tool_name,
        description=description,
        skills_provided=skills,
        parameters=parameters,
        function=call_mcp_tool,
        risk_level=risk_level,
        source_type="mcp",
        server_or_host=server_id,
    )

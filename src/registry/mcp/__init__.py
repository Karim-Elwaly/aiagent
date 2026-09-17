"""Model Context Protocol (MCP) Integration for UAOS."""

from src.registry.mcp.mcp_adapter import mcp_tool_to_tool_spec
from src.registry.mcp.mcp_client import MCPClient

__all__ = ["MCPClient", "mcp_tool_to_tool_spec"]

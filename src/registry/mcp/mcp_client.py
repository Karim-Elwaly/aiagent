"""Model Context Protocol (MCP) Client.

Supports stdio (subprocess) and SSE (HTTP) transports to connect to any
standard MCP server (e.g. GitHub, PostgreSQL, Slack, SQLite, Filesystem).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
from typing import Any

import httpx

from src.core.exceptions import ToolExecutionError

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for Model Context Protocol (MCP) servers.

    Can connect via:
      - stdio: runs a local process (e.g., npx @modelcontextprotocol/server-sqlite)
      - sse: connects to a remote HTTP/SSE MCP server endpoint
    """

    def __init__(
        self,
        server_id: str,
        transport: str = "stdio",  # "stdio" | "sse"
        command: str | None = None,  # e.g., "npx -y @modelcontextprotocol/server-postgres"
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.server_id = server_id
        self.transport = transport.lower()
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.url = url
        self.timeout_seconds = timeout_seconds

        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._connected = False
        self._http_client: httpx.AsyncClient | None = None
        self._tools_cache: list[dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Establish connection to the MCP server and complete handshake."""
        if self._connected:
            return

        if self.transport == "stdio":
            await self._connect_stdio()
        elif self.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unsupported MCP transport: '{self.transport}'")

        # Handshake: initialize
        await self._initialize()
        self._connected = True
        logger.info("Connected to MCP server '%s' via %s", self.server_id, self.transport)

    async def _connect_stdio(self) -> None:
        if not self.command:
            raise ValueError("Command is required for stdio MCP transport")

        full_cmd = []
        # Support space-separated command in string or list of args
        parts = shlex.split(self.command) if isinstance(self.command, str) else list(self.command)
        full_cmd.extend(parts)
        if self.args:
            full_cmd.extend(self.args)

        # Merge environment variables
        process_env = os.environ.copy()
        process_env.update(self.env)

        try:
            self._process = await asyncio.create_subprocess_exec(
                full_cmd[0],
                *full_cmd[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
            )
        except Exception as e:
            logger.error("Failed to spawn MCP process '%s': %s", full_cmd, e)
            raise ConnectionError(f"Failed to start MCP server process: {e}") from e

    async def _connect_sse(self) -> None:
        if not self.url:
            raise ValueError("URL is required for SSE MCP transport")
        self._http_client = httpx.AsyncClient(timeout=self.timeout_seconds)

    async def _send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        self._request_id += 1
        req_id = self._request_id
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        if self.transport == "stdio":
            return await self._send_stdio(payload)
        elif self.transport == "sse":
            return await self._send_sse(payload)
        raise ValueError(f"Unknown transport {self.transport}")

    async def _send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        if self.transport == "stdio" and self._process and self._process.stdin:
            message = json.dumps(payload) + "\n"
            self._process.stdin.write(message.encode("utf-8"))
            await self._process.stdin.drain()
        elif self.transport == "sse" and self._http_client and self.url:
            await self._http_client.post(self.url, json=payload)

    async def _send_stdio(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise ConnectionError("MCP stdio process is not running")

        message = json.dumps(payload) + "\n"
        self._process.stdin.write(message.encode("utf-8"))
        await self._process.stdin.drain()

        # Read lines until we get the response with matching id
        deadline = asyncio.get_event_loop().time() + self.timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            remaining = max(0.1, deadline - asyncio.get_event_loop().time())
            try:
                line_bytes = await asyncio.wait_for(self._process.stdout.readline(), timeout=remaining)
            except TimeoutError:
                raise TimeoutError(f"MCP server '{self.server_id}' timed out waiting for response") from None

            if not line_bytes:
                raise ConnectionError(f"MCP server '{self.server_id}' closed connection unexpectedly")

            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                if data.get("id") == payload["id"]:
                    if "error" in data:
                        err = data["error"]
                        raise ToolExecutionError(
                            self.server_id,
                            f"MCP Error ({err.get('code', 'unknown')}): {err.get('message', '')}",
                        )
                    return data.get("result", {})
            except json.JSONDecodeError:
                logger.debug("Non-JSON line from MCP server stdout: %s", line)
                continue

        raise TimeoutError(f"Timed out waiting for response from MCP server '{self.server_id}'")

    async def _send_sse(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._http_client or not self.url:
            raise ConnectionError("MCP HTTP client not initialized")

        resp = await self._http_client.post(self.url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            err = data["error"]
            raise ToolExecutionError(
                self.server_id,
                f"MCP Error ({err.get('code', 'unknown')}): {err.get('message', '')}",
            )
        return data.get("result", {})

    async def _initialize(self) -> None:
        """Perform MCP initialize handshake."""
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "uaos-client",
                "version": "0.1.0",
            },
        }
        await self._send_request("initialize", init_params)
        await self._send_notification("notifications/initialized")

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch all available tools from the MCP server."""
        result = await self._send_request("tools/list", {})
        tools = result.get("tools", [])
        self._tools_cache = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call an MCP tool and return its text content or stringified result."""
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })

        # MCP spec returns { content: [ { type: "text", text: "..." }, ... ], isError?: bool }
        is_error = result.get("isError", False)
        content_items = result.get("content", [])

        extracted = []
        for item in content_items:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    extracted.append(item.get("text", ""))
                elif item.get("type") == "image":
                    extracted.append(f"[Image: {item.get('mimeType', 'unknown')}]")
                elif item.get("type") == "resource":
                    extracted.append(str(item.get("resource", {})))
                else:
                    extracted.append(str(item))
            else:
                extracted.append(str(item))

        output = "\n".join(extracted) if extracted else json.dumps(result, indent=2)
        if is_error:
            raise ToolExecutionError(name, f"MCP Tool returned error:\n{output}")
        return output

    async def close(self) -> None:
        """Terminate process or close HTTP client."""
        self._connected = False
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except Exception as term_err:
                logger.debug("Process termination failed: %s, attempting kill", term_err)
                try:
                    self._process.kill()
                except Exception as kill_err:
                    logger.debug("Process kill error: %s", kill_err)
            self._process = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        logger.info("Closed MCP server '%s'", self.server_id)

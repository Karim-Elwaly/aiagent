from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from itertools import count
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from app.core.config import settings

_SESSION_TOKEN_PATTERN = re.compile(
    r'window\.__HERMES_SESSION_TOKEN__\s*=\s*("(?:\\.|[^"\\])*")'
)
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class HermesGatewayError(RuntimeError):
    """Safe-to-log gateway error; never includes the credential or frame payload."""


class HermesGatewayClient:
    def __init__(self, base_url: str, session_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token or None
        self._socket: ClientConnection | None = None
        self._request_ids = count(1)

    @property
    def _parsed_base(self):
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise HermesGatewayError("Hermes base URL must use http(s) and include a host.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HermesGatewayError("Hermes base URL must not embed credentials or query parameters.")
        return parsed

    def _uses_compose_bridge(self, parsed) -> bool:
        return (
            settings.hermes_loopback_bridge_enabled
            and not settings.auth_required
            and parsed.scheme == "http"
            and bool(parsed.hostname)
            and parsed.hostname.lower() == "host.docker.internal"
        )

    async def _resolve_session_token(self) -> str:
        if self.session_token:
            return self.session_token
        parsed = self._parsed_base
        loopback_host = parsed.hostname.lower() in _LOOPBACK_HOSTS
        compose_bridge_host = self._uses_compose_bridge(parsed)
        if not loopback_host and not compose_bridge_host:
            raise HermesGatewayError(
                "Hermes loopback token discovery is restricted to localhost; configure a supported "
                "service credential for remote gateways."
            )
        root_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + "/", "", ""))
        try:
            headers = {"Host": f"127.0.0.1:{parsed.port}"} if compose_bridge_host else None
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.get(root_url, headers=headers)
        except httpx.HTTPError as error:
            raise HermesGatewayError("Hermes dashboard is unreachable.") from error
        match = _SESSION_TOKEN_PATTERN.search(response.text) if response.is_success else None
        if not match:
            raise HermesGatewayError(
                "Hermes did not expose its loopback SPA session token; the dashboard may require OIDC."
            )
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as error:
            raise HermesGatewayError("Hermes returned a malformed loopback session bootstrap.") from error

    async def __aenter__(self) -> HermesGatewayClient:
        parsed = self._parsed_base
        token = await self._resolve_session_token()
        scheme = "wss" if parsed.scheme == "https" else "ws"
        compose_bridge = self._uses_compose_bridge(parsed)
        ws_host = "127.0.0.1" if compose_bridge else parsed.hostname
        ws_netloc = f"{ws_host}:{parsed.port}" if parsed.port else str(ws_host)
        path = parsed.path.rstrip("/") + "/api/ws"
        query = urlencode({"token": token})
        ws_url = urlunsplit((scheme, ws_netloc, path, query, ""))
        try:
            self._socket = await websockets.connect(
                ws_url,
            host=parsed.hostname if compose_bridge else None,
            port=parsed.port,
                open_timeout=8,
                close_timeout=2,
                max_size=4 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=20,
            )
            await self._wait_until_ready()
        except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError) as error:
            await self._close()
            raise HermesGatewayError("Could not authenticate to the Hermes JSON-RPC WebSocket.") from error
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self._close()

    async def _close(self) -> None:
        if self._socket is not None:
            socket, self._socket = self._socket, None
            await socket.close()

    async def _receive_frame(self, timeout: float) -> dict:
        if self._socket is None:
            raise HermesGatewayError("Hermes WebSocket is not connected.")
        try:
            raw = await asyncio.wait_for(self._socket.recv(), timeout=timeout)
            frame = json.loads(raw)
        except (asyncio.TimeoutError, json.JSONDecodeError, websockets.exceptions.WebSocketException) as error:
            raise HermesGatewayError("Invalid or timed-out Hermes JSON-RPC frame.") from error
        if not isinstance(frame, dict):
            raise HermesGatewayError("Hermes returned a non-object JSON-RPC frame.")
        return frame

    async def _wait_until_ready(self) -> None:
        for _ in range(10):
            frame = await self._receive_frame(timeout=5)
            params = frame.get("params") or {}
            if frame.get("method") == "event" and params.get("type") == "gateway.ready":
                return
        raise HermesGatewayError("Hermes did not send its gateway.ready event.")

    async def call(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        if self._socket is None:
            raise HermesGatewayError("Hermes WebSocket is not connected.")
        request_id = next(self._request_ids)
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        try:
            await self._socket.send(json.dumps(request, separators=(",", ":")))
            while True:
                frame = await self._receive_frame(timeout=timeout)
                if frame.get("id") != request_id:
                    continue
                error = frame.get("error")
                if error:
                    message = error.get("message", "Hermes RPC failed") if isinstance(error, dict) else "Hermes RPC failed"
                    raise HermesGatewayError(f"Hermes RPC {method} failed: {message}")
                result = frame.get("result")
                if not isinstance(result, dict):
                    raise HermesGatewayError(f"Hermes RPC {method} returned an invalid result.")
                return result
        except HermesGatewayError:
            raise
        except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError) as error:
            raise HermesGatewayError(f"Hermes RPC {method} could not complete.") from error


@asynccontextmanager
async def connected_hermes() -> AsyncIterator[HermesGatewayClient]:
    client = HermesGatewayClient(settings.hermes_base_url, settings.hermes_api_token)
    async with client:
        yield client
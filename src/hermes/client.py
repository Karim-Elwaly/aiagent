"""
Async client for the Hermes Agent API server (``/v1/runs`` and friends, hermes-agent 0.21.5).

Named profiles are served under ``/p/<profile>/`` by a multiplexed gateway and each checks its own
``API_SERVER_KEY``. Run events arrive as SSE frames: ``id: <seq>`` then ``data: <json>``.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import AsyncIterator
from typing import Any

import httpx

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})
TERMINAL_EVENTS = frozenset(f"run.{s}" for s in TERMINAL_STATUSES)
# Sampling-dependent model-server faults, e.g. LM Studio rejecting a gpt-oss harmony message it can't parse.
MODEL_ERROR = re.compile(
    r"server_error|\"code\"\s*:\s*5\d\d|error code:?\s*5\d\d|does not match the expected|predict stream", re.I
)
MODEL_ERROR_RETRIES = 2


class HermesAPIError(RuntimeError):
    """The Hermes API answered with an error that retrying will not fix."""


def profile_prefix(profile: str | None) -> str:
    if profile in (None, "", "default"):
        return ""
    return "/p/" + urllib.parse.quote(profile, safe="")


class HermesClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _url(self, profile: str | None, path: str) -> str:
        return f"{self.base_url}{profile_prefix(profile)}{path}"

    @staticmethod
    def _headers(key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}"}

    @staticmethod
    def _check(resp: httpx.Response, what: str) -> Any:
        if resp.status_code in (401, 403):
            raise HermesAPIError(
                f"{what}: Hermes rejected the profile's API key ({resp.status_code}). "
                "If the profile was just created, restart the gateway: hermes gateway restart"
            )
        if resp.status_code >= 500 or resp.status_code in (408, 429):
            resp.raise_for_status()
        if resp.status_code >= 400:
            raise HermesAPIError(f"{what} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    async def _request(self, method: str, url: str, key: str, what: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.request(method, url, headers=self._headers(key), **kwargs)
        return self._check(resp, what)

    async def create_run(
        self, profile: str, key: str, input_text: str, instructions: str | None = None, session_id: str | None = None
    ) -> str:
        body: dict[str, Any] = {"input": input_text}
        if instructions:
            body["instructions"] = instructions
        if session_id:
            body["session_id"] = session_id
        data = await self._request("POST", self._url(profile, "/v1/runs"), key, "create run", json=body)
        run_id = data.get("run_id")
        if not run_id:
            raise HermesAPIError(f"Hermes did not start the run: {str(data)[:300]}")
        return run_id

    async def get_run(self, profile: str, key: str, run_id: str) -> dict[str, Any]:
        return await self._request("GET", self._url(profile, f"/v1/runs/{run_id}"), key, "run status")

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                return (await client.get(f"{self.base_url}/health")).status_code == 200
        except httpx.HTTPError:
            return False

    async def respond_approval(
        self, profile: str, key: str, run_id: str, choice: str, request_id: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"choice": choice}
        if request_id:
            body["request_id"] = request_id
        return await self._request(
            "POST", self._url(profile, f"/v1/runs/{run_id}/approval"), key, "approval", json=body
        )

    async def stop_run(self, profile: str, key: str, run_id: str) -> None:
        await self._request("POST", self._url(profile, f"/v1/runs/{run_id}/stop"), key, "stop run")

    async def toolsets(self, profile: str, key: str) -> list[dict[str, Any]]:
        data = await self._request("GET", self._url(profile, "/v1/toolsets"), key, "toolsets")
        rows = data.get("data", data) if isinstance(data, dict) else data
        return [r for r in rows or [] if isinstance(r, dict)]

    async def events(self, profile: str, key: str, run_id: str, last_seq: int = -1) -> AsyncIterator[dict[str, Any]]:
        """The run's events, oldest first, until Hermes closes the stream. Each carries its ``seq``."""
        params = {"last_seq": str(last_seq)} if last_seq >= 0 else None
        timeout = httpx.Timeout(self.timeout, read=90.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "GET", self._url(profile, f"/v1/runs/{run_id}/events"), headers=self._headers(key), params=params
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    self._check(resp, "run events")
                data_lines: list[str] = []
                async for line in resp.aiter_lines():
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                        continue
                    if line == "" and data_lines:
                        try:
                            event = json.loads("\n".join(data_lines))
                        except ValueError:
                            event = None
                        data_lines = []
                        if isinstance(event, dict):
                            yield event

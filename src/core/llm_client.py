"""
UAOS Local LLM Client

Thin async HTTP client for local LLM inference servers.
Compatible with any server exposing the OpenAI-compatible
/v1/chat/completions endpoint:
  - Ollama
  - vLLM
  - LM Studio
  - llama.cpp server
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import httpx

from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# HTTP statuses worth retrying: the server is momentarily unavailable/overloaded.
# 4xx like 400/413 are deterministic (e.g. context overflow) — retrying is futile.
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

_CAPABILITY_CACHE: dict[tuple[str, str], str] = {}


@dataclass
class LLMResponse:
    """Structured response from the LLM cleanly separating content, reasoning, and tool calls."""

    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def extract_thinking_and_content(raw_text: str) -> tuple[str, str]:
    """Extract <think>...</think> reasoning blocks from text.

    Returns (cleaned_content, reasoning_trace) ensuring model reasoning
    does not leak into final answers or content channels.
    """
    if not raw_text or "<think>" not in raw_text:
        return raw_text or "", ""

    parts = []
    thoughts = []
    curr = raw_text
    while "<think>" in curr:
        before, rest = curr.split("<think>", 1)
        if before:
            parts.append(before)
        if "</think>" in rest:
            thought, curr = rest.split("</think>", 1)
            thoughts.append(thought.strip())
        else:
            thoughts.append(rest.strip())
            curr = ""
            break
    if curr:
        parts.append(curr)

    return "".join(parts).strip(), "\n\n".join(thoughts).strip()


def _is_retryable_error(exc: BaseException) -> bool:
    """True when an LLM call failure is transient and worth retrying.

    Connection drops, timeouts, protocol errors and 5xx/overload statuses are
    transient (server restarting, model reloading, network blip). Malformed
    requests (4xx other than the throttle codes) and empty-choice ``ValueError``
    are deterministic and would just repeat.
    """
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            httpx.ReadError,
            httpx.NetworkError,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


class LocalLLMClient:
    """Async client for local LLM chat completions with native tool calling support.

    Uses the OpenAI-compatible API format, which is the de facto
    standard for local inference servers.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "hermes3",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        max_retries: int = 2,
        retry_initial_interval: float = 1.0,
        retry_backoff: float = 2.0,
        retry_max_interval: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_initial_interval = retry_initial_interval
        self.retry_backoff = retry_backoff
        self.retry_max_interval = retry_max_interval

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion request returning clean assistant text."""
        res = await self.chat_with_tools(messages, tools=None)
        return res.content

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request with structured tool calls and reasoning separation."""
        interval = self.retry_initial_interval
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self._chat_with_tools_once(messages, tools=tools, max_tokens=max_tokens)
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries or not _is_retryable_error(exc):
                    raise
                logger.warning(
                    "LLM chat_with_tools transient failure (%s: %s); retry %d/%d in %.1fs",
                    type(exc).__name__,
                    exc,
                    attempt + 1,
                    self.max_retries,
                    interval,
                )
                await asyncio.sleep(interval)
                interval = min(interval * self.retry_backoff, self.retry_max_interval)
        assert last_exc is not None
        raise last_exc

    async def _chat_with_tools_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Execute a single HTTP request to /v1/chat/completions."""
        effective_max_tokens = max_tokens or self.max_tokens

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": effective_max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        logger.debug(
            "LLM request (direct): model=%s, messages=%d, tools=%s, max_tokens=%d",
            self.model,
            len(messages),
            len(tools) if tools else 0,
            effective_max_tokens,
        )

        timeout_config = httpx.Timeout(
            timeout=max(self.timeout, 300.0),
            connect=30.0,
            read=max(self.timeout, 300.0),
            write=60.0,
        )

        async with httpx.AsyncClient(timeout=timeout_config) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            if resp.is_error:
                # The server's body carries the real reason (context overflow, model not loaded, bad template).
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} from {resp.request.url} (model={self.model}, messages={len(messages)}, "
                    f"prompt_chars={sum(len(str(m.get('content') or '')) for m in messages)}): {resp.text[:1000]}",
                    request=resp.request,
                    response=resp,
                )
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"LLM returned no choices in response: {data}")

        choice = choices[0]
        message = choice.get("message", {})
        raw_content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        tool_calls = message.get("tool_calls") or []
        finish_reason = choice.get("finish_reason", "stop")

        # Channel separation: extract <think> blocks if present in raw_content
        cleaned_content, extracted_thinking = extract_thinking_and_content(raw_content)
        if extracted_thinking:
            reasoning = f"{reasoning}\n\n{extracted_thinking}".strip() if reasoning else extracted_thinking

        logger.debug(
            "LLM response: %d chars, %d tool calls, finish_reason=%s",
            len(cleaned_content),
            len(tool_calls),
            finish_reason,
        )
        if finish_reason == "length":
            logger.warning(
                "LLM reply cut off at max_tokens=%d (model=%s, content %d chars, reasoning %d chars)",
                effective_max_tokens, self.model, len(cleaned_content), len(reasoning),
            )

        return LLMResponse(
            content=cleaned_content,
            reasoning=reasoning,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )

    async def probe_capability(self) -> str:
        """Probe whether the inference server supports native OpenAI-style tool calls.

        Returns one of: 'native' | 'tags' | 'legacy'
        """
        from src.core.config import get_settings
        settings = get_settings()
        mode = getattr(settings, "tool_call_mode", "legacy")
        if mode in ("native", "tags", "legacy"):
            return mode

        key = (self.base_url, self.model)
        if key in _CAPABILITY_CACHE:
            return _CAPABILITY_CACHE[key]

        test_tool = {
            "type": "function",
            "function": {
                "name": "probe_tool",
                "description": "Probe test tool",
                "parameters": {
                    "type": "object",
                    "properties": {"test": {"type": "string"}},
                },
            },
        }
        test_msgs = [
            {"role": "user", "content": "Call the probe_tool with test='hello'."}
        ]
        try:
            res = await self._chat_with_tools_once(test_msgs, tools=[test_tool], max_tokens=150)
            if res.tool_calls:
                _CAPABILITY_CACHE[key] = "native"
                logger.info("Probe detected native tool-calling support on %s (%s)", self.base_url, self.model)
                return "native"
            if "<tool_call>" in res.content:
                _CAPABILITY_CACHE[key] = "tags"
                logger.info("Probe detected Hermes XML tags tool-calling support on %s (%s)", self.base_url, self.model)
                return "tags"
        except Exception as e:
            logger.debug("Probe failed on %s: %s; falling back to legacy", self.base_url, e)

        _CAPABILITY_CACHE[key] = "legacy"
        return "legacy"


    async def chat_stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens chunk-by-chunk via Server-Sent Events (SSE).

        Yields:
            Individual token strings as they arrive from the inference server.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        logger.debug(
            "LLM stream request: model=%s, messages=%d",
            self.model,
            len(messages),
        )

        timeout_config = httpx.Timeout(
            timeout=max(self.timeout, 300.0),
            connect=30.0,
            read=max(self.timeout, 300.0),
            write=60.0,
        )

        async with (
            httpx.AsyncClient(timeout=timeout_config) as client,
            client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
            ) as resp,
        ):
            resp.raise_for_status()
            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            # Harmony models (gpt-oss) emit most output on the reasoning channel.
                            content = (
                                delta.get("content")
                                or delta.get("reasoning_content")
                                or delta.get("text")
                                or ""
                            )
                            if content:
                                yield str(content)
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> bool:
        """Check if the LLM server is reachable.

        Returns True if the server responds, False otherwise.
        """
        urls_to_try = [
            f"{self.base_url}/models",
            self.base_url,
        ]
        if self.base_url.endswith("/v1"):
            parent = self.base_url[:-3]
            urls_to_try.extend([f"{parent}/api/tags", parent])

        for url in urls_to_try:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(url)
                    if resp.status_code in (200, 204, 301, 302, 307, 308):
                        return True
            except Exception:
                continue
        return False

    async def list_models(self) -> list[str]:
        """Fetch list of available model identifiers from the server.

        Compatible with OpenAI /v1/models response format used by LM Studio, Ollama, vLLM.
        """
        urls_to_try = [f"{self.base_url}/models"]
        if self.base_url.endswith("/v1"):
            urls_to_try.append(f"{self.base_url[:-3]}/api/tags")

        for url in urls_to_try:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        # Handle {"data": [{"id": "..."}, ...]} (OpenAI/LM Studio format)
                        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                            models = [m["id"] for m in data["data"] if "id" in m]
                            if models:
                                return models
                        # Handle Ollama {"models": [{"name": "..."}, ...]} format
                        if isinstance(data, dict) and "models" in data and isinstance(data["models"], list):
                            models = [m["name"] for m in data["models"] if "name" in m]
                            if models:
                                return models
            except Exception as e:
                logger.debug("Failed to list models from %s: %s", url, e)
        return []


    def __repr__(self) -> str:
        return (
            f"LocalLLMClient(base_url='{self.base_url}', "
            f"model='{self.model}')"
        )

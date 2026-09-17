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

import json
import logging
from collections.abc import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class LocalLLMClient:
    """Async client for local LLM chat completions.

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
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Send a chat completion request.

        Uses streaming internally to receive response headers immediately
        from local inference servers (avoiding ReadTimeout on large models like 27B/70B),
        and falls back to non-streaming if needed.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            The assistant's response text.
        """
        # First attempt: stream accumulation to avoid long header wait timeouts
        try:
            tokens = []
            async for token in self.chat_stream(messages):
                tokens.append(token)
            if tokens:
                content = "".join(tokens)
                logger.debug("LLM stream completed: %d chars", len(content))
                return content
        except Exception as stream_err:
            logger.debug("Streaming chat attempt failed, trying direct POST: %s", stream_err)

        # Fallback to direct POST
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        logger.debug(
            "LLM request (direct): model=%s, messages=%d, max_tokens=%d",
            self.model,
            len(messages),
            self.max_tokens,
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
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]

        logger.debug(
            "LLM response: %d chars, finish_reason=%s",
            len(content),
            data["choices"][0].get("finish_reason", "unknown"),
        )

        return content

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
                            content = delta.get("content", "")
                            if content:
                                yield content
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

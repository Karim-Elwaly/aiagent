"""Unit tests for LLM client retry-with-backoff and error classification."""

import httpx
import pytest

from src.core.llm_client import LocalLLMClient, _is_retryable_error


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://llm.local/v1/chat/completions")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"status {code}", request=request, response=response)


# ── classification ───────────────────────────────────────────────
def test_connection_errors_are_retryable():
    assert _is_retryable_error(httpx.ConnectError("refused"))
    assert _is_retryable_error(httpx.ReadTimeout("slow"))
    assert _is_retryable_error(httpx.RemoteProtocolError("dropped"))


@pytest.mark.parametrize("code", [500, 502, 503, 504, 429, 408])
def test_5xx_and_throttle_are_retryable(code):
    assert _is_retryable_error(_http_status_error(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404, 413, 422])
def test_client_errors_are_not_retryable(code):
    # 400/413 = deterministic (e.g. context overflow); retrying is futile.
    assert not _is_retryable_error(_http_status_error(code))


def test_value_error_not_retryable():
    assert not _is_retryable_error(ValueError("no choices"))


# ── retry loop ───────────────────────────────────────────────────
def _fast_client(max_retries: int) -> LocalLLMClient:
    return LocalLLMClient(
        base_url="http://llm.local/v1",
        model="test",
        max_retries=max_retries,
        retry_initial_interval=0.0,  # no real waiting in tests
        retry_backoff=1.0,
        retry_max_interval=0.0,
    )


@pytest.mark.asyncio
async def test_chat_retries_transient_then_succeeds(monkeypatch):
    client = _fast_client(max_retries=3)
    calls = {"n": 0}

    async def flaky(messages):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("server restarting")
        return "recovered answer"

    monkeypatch.setattr(client, "_chat_once", flaky)
    result = await client.chat([{"role": "user", "content": "hi"}])
    assert result == "recovered answer"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_chat_gives_up_after_max_retries(monkeypatch):
    client = _fast_client(max_retries=2)
    calls = {"n": 0}

    async def always_down(messages):
        calls["n"] += 1
        raise httpx.ConnectError("still down")

    monkeypatch.setattr(client, "_chat_once", always_down)
    with pytest.raises(httpx.ConnectError):
        await client.chat([{"role": "user", "content": "hi"}])
    # initial attempt + 2 retries
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_chat_does_not_retry_deterministic_error(monkeypatch):
    client = _fast_client(max_retries=5)
    calls = {"n": 0}

    async def bad_request(messages):
        calls["n"] += 1
        raise _http_status_error(400)

    monkeypatch.setattr(client, "_chat_once", bad_request)
    with pytest.raises(httpx.HTTPStatusError):
        await client.chat([{"role": "user", "content": "hi"}])
    # No retries for a 400 — fail fast.
    assert calls["n"] == 1

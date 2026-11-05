import pytest

from app.core.config import settings
from app.services import hermes_runtime


class FakeHermes:
    def __init__(self, snapshots: list[dict]):
        self.snapshots = list(snapshots)
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        self.calls.append((method, params or {}))
        if method == "session.resume":
            return self.snapshots.pop(0)
        raise AssertionError(f"Unexpected RPC: {method}")


@pytest.mark.asyncio
async def test_wait_for_turn_resumes_with_stored_id_and_returns_runtime_id():
    hermes = FakeHermes(
        [
            {"session_id": "runtime-1", "status": "working", "running": True},
            {"session_id": "runtime-1", "status": "idle", "running": False},
        ]
    )

    snapshot = await hermes_runtime.wait_for_turn(
        hermes, "stored-1", timeout_seconds=5, poll_interval=0.01
    )

    assert snapshot["session_id"] == "runtime-1"
    assert [params["session_id"] for _, params in hermes.calls] == ["stored-1", "stored-1"]


@pytest.mark.asyncio
async def test_wait_for_turn_ignores_pre_submit_idle_snapshot():
    hermes = FakeHermes(
        [
            {"session_id": "runtime-1", "status": "idle", "running": False},
            {"session_id": "runtime-1", "status": "working", "running": True},
            {"session_id": "runtime-1", "status": "idle", "running": False},
        ]
    )

    await hermes_runtime.wait_for_turn(
        hermes, "stored-1", timeout_seconds=5, poll_interval=0.01
    )

    assert len(hermes.calls) == 3


def test_session_create_params_include_workspace_and_model(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "hermes_home", str(tmp_path))
    monkeypatch.setattr(settings, "hermes_model", "openai/gpt-oss-20b")
    monkeypatch.setattr(settings, "hermes_provider", "gpu")

    params = hermes_runtime.session_create_params("Runtime test")

    assert params["cwd"] == str(tmp_path)
    assert params["model"] == "openai/gpt-oss-20b"
    assert params["provider"] == "gpu"
    assert tmp_path.exists()


def test_history_extraction_reads_content_and_tool_calls():
    history = {
        "messages": [
            {"role": "tool", "name": "read_file", "content": "source"},
            {"role": "assistant", "content": [{"type": "text", "text": "final answer"}]},
            {"role": "assistant", "tool_calls": [{"function": {"name": "terminal"}}]},
        ]
    }

    assert hermes_runtime.assistant_text(history) == "final answer"
    assert hermes_runtime.tool_names(history) == ["read_file", "terminal"]

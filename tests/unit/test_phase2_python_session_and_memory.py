"""
Unit tests for Phase 2:
- Stateful Persistent Python Environment (REPL session, variable persistence, reset, journal replay)
- Long-Term Memory Store (SQLite + FTS5, secret masking, grounding verification, web quarantine, volatile facts)
- Memory Retriever & MetaPlanner prompt integration
- Hermes session_search integration with memory store
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import Settings
from src.core.tool_context import ToolContext, set_tool_context, reset_tool_context
from src.memory.retriever import MemoryRetriever
from src.memory.store import Episode, Fact, Lesson, MemoryStore, mask_secrets
from src.registry.tools.hermes_tools import session_search
from src.registry.tools.python_session import (
    PersistentPythonSession,
    get_or_create_session,
    python_session,
    reset_session,
)


# ── 1. Python Session State & Variable Persistence ────────────────


@pytest.mark.asyncio
async def test_python_session_variable_persistence():
    """Verify that variables set in one call are accessible in subsequent calls in the same session."""
    session = PersistentPythonSession(workflow_id="test_wf_var")
    try:
        res1 = await session.execute("x = 42\ny = 'hello'")
        assert res1["success"] is True

        res2 = await session.execute("result = x * 2; print(f'{y}_{result}')")
        assert res2["success"] is True
        assert "hello_84" in res2["stdout"]

        # Inspect variables
        vars_res = await session.execute("__vars__")
        vars_data = session.inspect_vars()
        assert vars_data.get("x") == "42"
        assert "'hello'" in vars_data.get("y", "")
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_python_session_reset():
    """Verify that reset clears all variables and restarts the execution environment."""
    session = PersistentPythonSession(workflow_id="test_wf_reset")
    try:
        await session.execute("secret_num = 999")
        assert "secret_num" in session.inspect_vars()

        reset_res = session.reset()
        assert reset_res["success"] is True
        assert "secret_num" not in session.inspect_vars()

        # Variable should no longer exist
        res = await session.execute("print(secret_num)")
        assert res["success"] is False
        assert "NameError" in res["stderr"] or "not defined" in res["stderr"]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_python_session_matplotlib_artifact(tmp_path):
    """Verify that matplotlib plots are saved as artifact images and returned in artifact_paths."""
    session = PersistentPythonSession(
        workflow_id="test_wf_plot",
        artifacts_dir=tmp_path / "artifacts" / "test_wf_plot",
        sessions_dir=tmp_path / "sessions",
    )
    try:
        code = (
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "plt.figure()\n"
            "plt.plot([1, 2, 3], [4, 5, 6])\n"
            "plt.title('Test Plot')\n"
        )
        res = await session.execute(code)
        assert res["success"] is True
        assert len(res["artifacts"]) >= 1
        artifact_path = Path(res["artifacts"][0])
        assert artifact_path.exists()
        assert artifact_path.suffix == ".png"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_python_session_journal_replay(tmp_path):
    """Verify that past execution journal can replay state into a new session instance."""
    sessions_dir = tmp_path / "sessions"
    wf_id = "test_wf_replay"

    # Step 1: Execute in session 1
    session1 = PersistentPythonSession(
        workflow_id=wf_id,
        sessions_dir=sessions_dir,
    )
    await session1.execute("accumulated_data = [10, 20, 30]")
    await session1.execute("accumulated_data.append(40)")
    await session1.close()

    # Step 2: Create new session for same workflow and replay journal
    session2 = PersistentPythonSession(
        workflow_id=wf_id,
        sessions_dir=sessions_dir,
    )
    recovered = await session2.recover_from_journal()
    assert recovered == 2

    # Verify state was re-established
    res = await session2.execute("print(sum(accumulated_data))")
    assert res["success"] is True
    assert "100" in res["stdout"]
    await session2.close()


@pytest.mark.asyncio
async def test_python_session_tool_wrapper_context():
    """Verify python_session tool function routes through ToolContext."""
    ctx = ToolContext(workflow_id="wf_tool_ctx", task_id="t1")
    token = set_tool_context(ctx)
    try:
        # Action run
        run_res = await python_session(action="run", code="val = 7 * 6; print(val)")
        assert "42" in run_res

        # Action inspect_vars
        vars_res = await python_session(action="inspect_vars")
        assert "val" in vars_res

        # Action reset
        reset_res = await python_session(action="reset")
        assert "reset" in reset_res.lower()
    finally:
        reset_tool_context(token)
        reset_session("wf_tool_ctx")


# ── 2. Memory Store & Grounding Verification ─────────────────────


def test_mask_secrets():
    """Verify that API keys, bearer tokens, and passwords are redacted."""
    raw = (
        "Here is the token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz123\n"
        "And the openai key: sk-abcdefghijklmnopqrstuvwxyz12345\n"
        "Config: api_key='1234567890abcdef123456'\n"
        "password = 'supersecretpass'"
    )
    masked = mask_secrets(raw)
    assert "[REDACTED_SECRET]" in masked
    assert "eyJhbGciOi" not in masked
    assert "sk-abcdef" not in masked
    assert "supersecretpass" not in masked


def test_memory_store_grounding_rejection(tmp_path):
    """Verify that unverified facts are rejected if evidence is missing from tool outputs."""
    db_file = tmp_path / "test_memory.db"
    store = MemoryStore(db_path=db_file)

    # 1. Fact without evidence or tool outputs -> Rejected
    unverified_fact = Fact(
        key="db_port",
        value="5432",
        evidence="port is 5432",
        provenance="tool",
    )
    saved = store.save_fact(unverified_fact, verified_grounding=False, tool_outputs=[])
    assert saved is False

    # 2. Fact with evidence not in tool outputs -> Rejected
    saved_false_ev = store.save_fact(
        unverified_fact,
        verified_grounding=False,
        tool_outputs=["System is up", "Hostname is test-host"],
    )
    assert saved_false_ev is False

    # 3. Fact with matching evidence -> Accepted
    saved_true_ev = store.save_fact(
        unverified_fact,
        verified_grounding=False,
        tool_outputs=["System is listening on port is 5432 for connections"],
    )
    assert saved_true_ev is True

    # 4. Fact explicitly verified (e.g. user set) -> Accepted
    user_fact = Fact(key="user_name", value="Alice", provenance="user")
    saved_user = store.save_fact(user_fact, verified_grounding=True)
    assert saved_user is True


def test_memory_store_web_quarantine(tmp_path):
    """Verify that facts from web sources are quarantined and excluded from general search."""
    db_file = tmp_path / "test_memory.db"
    store = MemoryStore(db_path=db_file)

    web_fact = Fact(
        key="framework_release",
        value="v2.5 released yesterday",
        evidence="v2.5 released yesterday",
        provenance="web",
    )
    store.save_fact(web_fact, verified_grounding=True)

    # Search should exclude quarantined facts
    matches = store.search_facts("framework")
    assert len(matches) == 0


def test_memory_store_volatile_facts_and_warning(tmp_path):
    """Verify that volatile keywords are flagged volatile and highlighted in retrieval context."""
    db_file = tmp_path / "test_memory.db"
    store = MemoryStore(db_path=db_file)

    # Fact with volatile keyword "ip_address"
    fact = Fact(
        key="primary_ip_address",
        value="192.168.1.100",
        evidence="192.168.1.100",
        provenance="tool",
    )
    store.save_fact(fact, verified_grounding=True)

    retriever = MemoryRetriever(store=store)
    ctx = retriever.build_context("primary_ip_address")

    assert "[VOLATILE]" in ctx
    assert "192.168.1.100" in ctx
    assert "Facts marked [VOLATILE]" in ctx
    assert "MUST be verified using tools" in ctx


def test_memory_store_episode_search(tmp_path):
    """Verify recording and FTS5 retrieval of past workflow episodes."""
    db_file = tmp_path / "test_memory.db"
    store = MemoryStore(db_path=db_file)

    episode = Episode(
        run_id="run-101",
        query="Deploy redis cluster on kubernetes",
        goal="Configure and deploy redis statefulset",
        dag_json="{}",
        outcome="accurate",
        score=1.0,
    )
    store.record_episode(episode)

    results = store.search_episodes("kubernetes redis")
    assert len(results) >= 1
    assert results[0]["run_id"] == "run-101"
    assert "redis" in results[0]["query"].lower()


@pytest.mark.asyncio
async def test_session_search_integration(tmp_path):
    """Verify hermes session_search returns results from SQLite memory store when enable_memory is True."""
    db_file = tmp_path / "test_memory.db"
    store = MemoryStore(db_path=db_file)

    ep = Episode(
        run_id="run-202",
        query="Benchmark postgres indexing throughput",
        goal="Run sysbench and analyze query execution times",
        dag_json="{}",
        outcome="accurate",
        score=1.0,
    )
    store.record_episode(ep)

    mock_settings = Settings(enable_memory=True)
    with patch("src.registry.tools.hermes_tools.get_settings", return_value=mock_settings), \
         patch("src.memory.store.get_memory_store", return_value=store):
        output = await session_search("postgres benchmark")
        assert "run-202" in output
        assert "Benchmark postgres indexing throughput" in output

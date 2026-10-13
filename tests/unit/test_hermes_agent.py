"""
Unit tests for the Hermes Agent integration: tool gate (MCP permissions), profile provisioning,
the run-event client and the Hermes Agent worker.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import pytest
import yaml

from src.core.agent_models import AgentProfile
from src.core.agent_store import AgentStore
from src.core.models import RiskLevel, Task, TaskStatus
from src.hermes.active_runs import ActiveRuns
from src.hermes.client import HermesClient
from src.hermes.mcp_server import (
    ADD_TO_AGENT,
    ALLOW_FOR_RUN,
    DENY,
    REQUEST_TOOL,
    MCPEndpoint,
    ToolDenied,
    ToolGate,
    tool_input_schema,
)
from src.hermes.profiles import HermesProfiles, ProfileInfo, ProfileState, profile_name, read_env_value
from src.hermes.skills import imported_skill, skill_documents
from src.registry.hermes.hermes_adapter import parse_skill_markdown
from src.registry.tool_registry import ToolRegistry, ToolSpec
from src.workers.hermes_agent_worker import HermesAgentWorker


async def _no_sleep(*args, **kwargs):
    return None


def _settings(**overrides):
    base = dict(
        hermes_api_url="http://127.0.0.1:8642",
        hermes_home="",
        hermes_bin="hermes",
        hermes_mcp_url="http://127.0.0.1:8000/mcp/",
        hermes_default_toolsets=["web"],
        hermes_run_timeout_seconds=30,
        hermes_approval_timeout_seconds=5,
        worker_max_output_chars=1000,
        worker_max_context_chars=12000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _spec(name, skills, fn=None, risk=RiskLevel.LOW, source="native"):
    async def default(**kwargs):
        return f"{name}:{sorted(kwargs.items())}"

    return ToolSpec(
        tool_id=f"{name}_v1", name=name, description=f"{name} tool. Does things.", skills_provided=skills,
        parameters={"path": {"type": "string", "required": True}, "n": {"type": "int"}},
        function=fn or default, risk_level=risk, source_type=source,
    )


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(_spec("list_directory", ["directory_listing"]))
    reg.register(_spec("read_file", ["file_reading"]))
    reg.register(_spec("execute_command", ["shell_command"], risk=RiskLevel.HIGH))
    reg.register(_spec("skill_echo", ["echo"], source="skill"))
    return reg


@pytest.fixture
def store(tmp_path):
    s = AgentStore(storage_dir=tmp_path / "agents")
    s.save(AgentProfile(id="soc", name="SOC", description="d", curated_skills=["directory_listing"]))
    return s


class Asker:
    def __init__(self, answer):
        self.answer, self.questions = answer, []

    async def __call__(self, question, choices, workflow_id, task_id, timeout):
        self.questions.append((question, choices, workflow_id, task_id))
        return self.answer


def _gate(registry, store, tmp_path, answer=DENY):
    active = ActiveRuns(tmp_path / "active")
    asker = Asker(answer)
    gate = ToolGate(registry, _settings(), state=ProfileState(tmp_path / "profiles.json"), active=active,
                    store=store, ask=asker)
    return gate, active, asker


SOC = {"profile": "aiagent-soc", "agent_id": "soc"}
DEFAULT = {"profile": "aiagent-default", "agent_id": ""}


# ── tool gate ─────────────────────────────────────────────────────


def test_exposed_tools_follow_agent_curation_and_hide_skill_echoes(registry, store, tmp_path):
    gate, _, _ = _gate(registry, store, tmp_path)
    assert [t.name for t in gate.exposed_tools(SOC)] == ["list_directory"]
    assert {t.name for t in gate.exposed_tools(DEFAULT)} == {"list_directory", "read_file", "execute_command"}


async def test_approved_tool_runs_without_asking(registry, store, tmp_path):
    gate, active, asker = _gate(registry, store, tmp_path)
    active.set("aiagent-soc", {"workflow_id": "wf1", "task_id": "t1", "task_tools": []})
    out = await gate.call(SOC, "list_directory", {"path": "D:\\x"})
    assert out.startswith("list_directory:")
    assert asker.questions == []


async def test_unapproved_tool_denied(registry, store, tmp_path):
    gate, active, asker = _gate(registry, store, tmp_path, answer=DENY)
    active.set("aiagent-soc", {"workflow_id": "wf1", "task_id": "t1", "task_tools": []})
    with pytest.raises(ToolDenied):
        await gate.call(SOC, "read_file", {"path": "a"})
    question, choices, wf, task = asker.questions[0]
    assert choices == [ADD_TO_AGENT, ALLOW_FOR_RUN, DENY] and (wf, task) == ("wf1", "t1")


async def test_allow_for_run_grants_only_this_workflow(registry, store, tmp_path):
    gate, active, asker = _gate(registry, store, tmp_path, answer=ALLOW_FOR_RUN)
    active.set("aiagent-soc", {"workflow_id": "wf1", "task_id": "t1", "task_tools": []})
    await gate.call(SOC, "read_file", {"path": "a"})
    await gate.call(SOC, "read_file", {"path": "b"})
    assert len(asker.questions) == 1
    assert store.load("soc").curated_skills == ["directory_listing"]
    active.set("aiagent-soc", {"workflow_id": "wf2", "task_id": "t1", "task_tools": []})
    asker.answer = DENY
    with pytest.raises(ToolDenied):
        await gate.call(SOC, "read_file", {"path": "c"})


async def test_add_to_agent_persists_the_skill(registry, store, tmp_path):
    gate, active, _ = _gate(registry, store, tmp_path, answer=ADD_TO_AGENT)
    active.set("aiagent-soc", {"workflow_id": "wf1", "task_id": "t1", "task_tools": []})
    await gate.call(SOC, "read_file", {"path": "a"})
    assert store.load("soc").curated_skills == ["directory_listing", "file_reading"]


async def test_default_profile_allows_task_tools_and_offers_no_agent_option(registry, store, tmp_path):
    gate, active, asker = _gate(registry, store, tmp_path, answer=DENY)
    active.set("aiagent-default", {"workflow_id": "wf1", "task_id": "t1", "task_tools": ["read_file"]})
    assert (await gate.call(DEFAULT, "read_file", {"path": "a"})).startswith("read_file:")
    with pytest.raises(ToolDenied):
        await gate.call(DEFAULT, "execute_command", {"path": "a"})
    assert asker.questions[0][1] == [ALLOW_FOR_RUN, DENY]


async def test_request_tool_runs_the_requested_tool_after_approval(registry, store, tmp_path):
    gate, active, asker = _gate(registry, store, tmp_path, answer=ALLOW_FOR_RUN)
    active.set("aiagent-soc", {"workflow_id": "wf1", "task_id": "t1", "task_tools": []})
    out = await gate.call(SOC, REQUEST_TOOL, {"tool_name": "read_file", "arguments": {"path": "a"}, "reason": "logs"})
    assert out.startswith("read_file:")
    assert "Reason given: logs" in asker.questions[0][0]


async def test_request_hermes_toolset_adds_to_agent_for_next_run(registry, store, tmp_path):
    gate, active, asker = _gate(registry, store, tmp_path, answer=ADD_TO_AGENT)
    active.set("aiagent-soc", {"workflow_id": "wf1", "task_id": "t1", "task_tools": []})
    out = await gate.call(SOC, REQUEST_TOOL, {"tool_name": "hermes:terminal", "reason": "run nslookup"})
    assert "next run" in out
    assert store.load("soc").hermes_toolsets == ["terminal"]
    assert asker.questions[0][1] == [ADD_TO_AGENT, DENY]


async def test_no_active_task_and_unknown_tool_are_refused(registry, store, tmp_path):
    gate, active, _ = _gate(registry, store, tmp_path)
    with pytest.raises(ToolDenied, match="No aiagent task"):
        await gate.call(SOC, "list_directory", {"path": "a"})
    active.set("aiagent-soc", {"workflow_id": "wf1", "task_id": "t1", "task_tools": []})
    with pytest.raises(ToolDenied, match="no tool named"):
        await gate.call(SOC, "skill_echo", {})


def test_input_schema_maps_required_and_types():
    schema = tool_input_schema(_spec("x", ["s"]))
    assert schema["required"] == ["path"]
    assert schema["properties"]["n"] == {"type": "integer"}


def test_input_schema_accepts_connector_json_schema():
    spec = _spec("c", ["s"])
    spec.parameters = {
        "type": "object",
        "properties": {"ip": {"type": "string"}, "days": {"type": "integer", "default": 90}},
        "required": ["ip"],
    }
    schema = tool_input_schema(spec)
    assert schema == {"type": "object", "required": ["ip"],
                      "properties": {"ip": {"type": "string"}, "days": {"type": "integer", "default": 90}}}


async def test_endpoint_rejects_remote_and_unauthenticated_callers(registry, store, tmp_path):
    gate, _, _ = _gate(registry, store, tmp_path)
    endpoint = MCPEndpoint(gate)
    sent = []

    async def send(message):
        sent.append(message)

    await endpoint({"type": "http", "client": ("10.0.0.5", 1), "headers": []}, None, send)
    await endpoint({"type": "http", "client": ("127.0.0.1", 1), "headers": [(b"authorization", b"Bearer nope")]},
                   None, send)
    assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [403, 401]


# ── profiles ──────────────────────────────────────────────────────


def test_profile_names():
    assert profile_name(None) == "aiagent-default"
    assert profile_name("Security Analyst!") == "aiagent-security-analyst"


def test_ensure_creates_profile_once_and_is_idempotent(tmp_path):
    home = tmp_path / "hermes"
    calls = []

    def runner(args):
        calls.append(args)
        if args[:2] == ["profile", "create"]:
            (home / "profiles" / args[2]).mkdir(parents=True)
        return ""

    state = ProfileState(tmp_path / "profiles.json")
    profiles = HermesProfiles(_settings(hermes_home=str(home)), runner=runner, state=state)
    info = profiles.ensure("soc", ["terminal", "bogus"], {"aiagent-x": "---\nname: x\n---\n"})
    env = home / "profiles" / "aiagent-soc" / ".env"
    assert info.changed and info.name == "aiagent-soc" and info.api_key == read_env_value(env, "API_SERVER_KEY")
    token = read_env_value(env, "AIAGENT_MCP_TOKEN")
    assert state.by_token(token)["agent_id"] == "soc"
    assert token not in (tmp_path / "profiles.json").read_text()
    assert ["profile", "create", "aiagent-soc", "--clone-from", "default", "--no-alias", "--description",
            "aiagent agent 'soc'"] in calls
    enable = next(c for c in calls if c[2:4] == ["tools", "enable"])
    assert enable[-3:] == ["skills", "terminal", "web"]
    assert any("Bearer ${AIAGENT_MCP_TOKEN}" in c for c in calls)
    assert ["-p", "aiagent-soc", "config", "set", "tools.tool_search.enabled", "off"] in calls
    skills_dir = (tmp_path / "skills" / "aiagent-soc").resolve()
    assert ["-p", "aiagent-soc", "config", "set", "skills.external_dirs", json.dumps([skills_dir.as_posix()])] in calls
    assert (skills_dir / "aiagent-x" / "SKILL.md").read_text() == "---\nname: x\n---\n"

    calls.clear()
    again = profiles.ensure("soc", ["terminal"], {})
    assert not again.changed and calls == []
    assert not (skills_dir / "aiagent-x").exists()


def test_toolset_change_does_not_wait_for_mcp(tmp_path):
    home = tmp_path / "hermes"
    (home / "profiles" / "aiagent-soc").mkdir(parents=True)
    calls = []
    profiles = HermesProfiles(_settings(hermes_home=str(home)), runner=lambda a: calls.append(a) or "",
                              state=ProfileState(tmp_path / "profiles.json"))
    profiles.ensure("soc", [])
    calls.clear()
    info = profiles.ensure("soc", ["terminal"])
    assert not info.changed
    assert any(c[2:4] == ["tools", "enable"] and "terminal" in c for c in calls)


def test_mcp_url_change_restarts_gateway(tmp_path):
    home = tmp_path / "hermes"
    (home / "profiles" / "aiagent-soc").mkdir(parents=True)
    calls = []
    state = ProfileState(tmp_path / "profiles.json")
    runner = lambda a: calls.append(a) or ""  # noqa: E731
    HermesProfiles(_settings(hermes_home=str(home)), runner=runner, state=state).ensure("soc", [])
    assert ["gateway", "restart"] not in calls

    calls.clear()
    moved = _settings(hermes_home=str(home), hermes_mcp_url="http://127.0.0.1:8001/mcp/")
    info = HermesProfiles(moved, runner=runner, state=state).ensure("soc", [])
    assert info.changed and ["gateway", "restart"] in calls
    assert ["-p", "aiagent-soc", "config", "set", "mcp_servers.aiagent.url", "http://127.0.0.1:8001/mcp/"] in calls

    calls.clear()
    assert not HermesProfiles(moved, runner=runner, state=state).ensure("soc", []).changed
    assert ["gateway", "restart"] not in calls


# ── skills ────────────────────────────────────────────────────────


def test_skill_documents_follow_curation_and_name_mcp_tools(registry, tmp_path):
    imported = tmp_path / "imported"
    imported.mkdir()
    (imported / "dir_guide.md").write_text(
        "---\nname: dir_guide\ndescription: How to walk folders.\nmetadata:\n  skills: [directory_listing]\n---\nWalk it.\n",
        encoding="utf-8")
    (imported / "unrelated.md").write_text("---\nname: unrelated\ndescription: Other.\n---\nNo.\n", encoding="utf-8")
    agent = AgentProfile(id="soc", name="SOC", description="d", curated_skills=["directory_listing"])

    docs = skill_documents(agent, registry, imported)
    assert sorted(docs) == ["aiagent-list-directory", "dir-guide"]
    meta, body = parse_skill_markdown(docs["aiagent-list-directory"])
    assert meta["name"] == "aiagent-list-directory" and "mcp__aiagent__list_directory" in meta["description"]
    assert "directory_listing" in meta["metadata"]["hermes"]["tags"]
    assert "`path` (string, required)" in body
    assert docs["dir-guide"].startswith("---\nname: dir_guide")

    everything = skill_documents(None, registry, imported)
    assert "aiagent-echo" not in everything  # skill-document echo tools are not MCP tools
    assert {"aiagent-read-file", "aiagent-execute-command", "unrelated"} <= set(everything)


def test_ensure_writes_soul_and_description_and_updates_on_change(tmp_path):
    home = tmp_path / "hermes"
    calls = []

    def runner(args):
        calls.append(args)
        if args[:2] == ["profile", "create"]:
            (home / "profiles" / args[2]).mkdir(parents=True)
        return ""

    profiles = HermesProfiles(_settings(hermes_home=str(home)), runner=runner,
                              state=ProfileState(tmp_path / "profiles.json"))
    agent = AgentProfile(id="soc", name="SOC", description="Investigates incidents",
                         system_prompt_template="You are SOC. Task: {task_name}. Tools: {tools}")
    profiles.ensure("soc", [], {}, agent=agent)
    soul = home / "profiles" / "aiagent-soc" / "SOUL.md"
    assert soul.read_text() == "You are SOC. Task: the task you are given. Tools: the tools available to you\n"
    assert ["profile", "create", "aiagent-soc", "--clone-from", "default", "--no-alias", "--description",
            "SOC: Investigates incidents"] in calls

    calls.clear()
    profiles.ensure("soc", [], {}, agent=agent)
    assert not any(c[:2] == ["profile", "describe"] for c in calls)

    agent.description = "Hunts threats"
    agent.system_prompt_template = "New persona"
    profiles.ensure("soc", [], {}, agent=agent)
    assert soul.read_text() == "New persona\n"
    assert ["profile", "describe", "aiagent-soc", "--text", "SOC: Hunts threats"] in calls


def test_imported_document_without_frontmatter_gets_one():
    meta, body = parse_skill_markdown(imported_skill("Just steps.", "My Guide", "Guide."))
    assert meta["name"] == "my-guide" and meta["description"] == "Guide." and body.strip() == "Just steps."


def test_imported_document_with_invalid_yaml_gets_valid_frontmatter():
    broken = "---\nname: chem\ndescription: Cheminformatics: parse SMILES.\n---\nSteps.\n"
    doc = imported_skill(broken, "chem", "ignored")
    meta = yaml.safe_load(doc.split("---", 2)[1])
    assert meta == {"name": "chem", "description": "Cheminformatics: parse SMILES.", "version": "1.0.0",
                    "author": "aiagent"}
    assert doc.rstrip().endswith("Steps.")


# ── client ────────────────────────────────────────────────────────


async def test_client_parses_sse_and_uses_profile_prefix(monkeypatch):
    seen = {}
    body = (
        ': open\n\n'
        'id: 0\ndata: {"event": "tool.started", "tool": "mcp__aiagent__read_file", "seq": 0}\n\n'
        ': keepalive\n\n'
        'id: 1\ndata: {"event": "run.completed", "output": "done", "seq": 1}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"] = str(request.url), request.headers["authorization"]
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    events = [e async for e in HermesClient("http://h:8642").events("aiagent-soc", "k", "run_1")]
    assert [e["event"] for e in events] == ["tool.started", "run.completed"]
    assert seen == {"url": "http://h:8642/p/aiagent-soc/v1/runs/run_1/events", "auth": "Bearer k"}


# ── worker ────────────────────────────────────────────────────────


class FakeClient:
    def __init__(self, events, final=None):
        self._events, self.final = events, final or {}
        self.created, self.approvals, self.stopped = [], [], []

    async def create_run(self, profile, key, input_text, instructions=None, session_id=None):
        self.created.append({"profile": profile, "input": input_text, "instructions": instructions,
                             "session_id": session_id})
        return "run_1"

    async def events(self, profile, key, run_id, last_seq=-1):
        for event in self._events:
            yield event

    async def get_run(self, profile, key, run_id):
        return self.final

    async def respond_approval(self, profile, key, run_id, choice, request_id=None):
        self.approvals.append((choice, request_id))

    async def stop_run(self, profile, key, run_id):
        self.stopped.append(run_id)

    async def healthy(self):
        self.health_checks = getattr(self, "health_checks", 0) + 1
        return True


class FakeProfiles:
    def __init__(self, connected=True, changed=True):
        self.ensured, self.restarts = [], 0
        self.connected, self.changed = connected, changed
        self.state = SimpleNamespace(mcp_connected=lambda name, since=0.0: self.connected)

    def ensure(self, agent_id, toolsets, skill_docs=None, agent=None, bundle=None):
        self.ensured.append((agent_id, toolsets))
        self.skill_docs = skill_docs
        return ProfileInfo(name=f"aiagent-{agent_id or 'default'}", api_key="k", changed=self.changed)

    def write_profile_skills(self, name, docs):
        self.written = (name, docs)

    def restart_gateway(self):
        self.restarts += 1
        self.connected = True


TASK = Task(id="t1", name="Scan", description="Scan logs", required_skills=["s"], expected_output="findings")


def _worker(tmp_path, events, final=None, answer="Allow once", agent=None):
    client = FakeClient(events, final)
    asker = Asker(answer)
    worker = HermesAgentWorker(_settings(), agent=agent, client=client, profiles=FakeProfiles(),
                               active=ActiveRuns(tmp_path / "active"), ask=asker)
    return worker, client, asker


async def test_worker_relays_events_and_returns_hermes_output(tmp_path):
    events = [
        {"event": "message.delta", "delta": "Look", "seq": 0},
        {"event": "tool.started", "tool": "mcp__aiagent__read_file", "preview": "{path}", "seq": 1},
        {"event": "tool.completed", "tool": "mcp__aiagent__read_file", "preview": "lines", "seq": 2},
        {"event": "run.completed", "output": "Found 3 IPs", "seq": 3},
    ]
    agent = AgentProfile(id="soc", name="SOC", description="d", hermes_toolsets=["terminal"])
    worker, client, _ = _worker(tmp_path, events, agent=agent)
    got, tokens, beats = [], [], []
    result = await worker.execute(TASK, "persona", [_spec("read_file", ["file_reading"])], user_query="case 1",
                                  on_token=tokens.append, on_event=got.append, on_heartbeat=beats.append,
                                  workflow_id="wf1")

    assert result.status == TaskStatus.COMPLETED and result.output == "Found 3 IPs"
    assert result.tool_calls_made == ["read_file"]
    assert tokens == ["Look"]
    assert [e["type"] for e in got] == ["tool_start", "tool_end", "final_answer"] and got[0]["tool"] == "read_file"
    assert client.created[0]["profile"] == "aiagent-soc" and client.created[0]["instructions"] == "persona"
    assert "case 1" in client.created[0]["input"] and "Scan logs" in client.created[0]["input"]
    assert worker.profiles.ensured == [("soc", ["terminal"])]
    assert beats[-1]["hermes_run_id"] == "run_1" and beats[-1]["engine"] == "hermes"
    assert ActiveRuns(tmp_path / "active").get("aiagent-soc") is None


async def test_worker_answers_hermes_approvals(tmp_path):
    events = [
        {"event": "approval.request", "description": "rm -rf", "choices": ["once", "session", "deny"],
         "request_id": "r1", "seq": 0},
        {"event": "tool.completed", "tool": "terminal", "seq": 1},
        {"event": "run.completed", "output": "ok", "seq": 2},
    ]
    worker, client, asker = _worker(tmp_path, events, answer="Allow for this run")
    result = await worker.execute(TASK, "p", [], workflow_id="wf1")
    assert client.approvals == [("session", "r1")]
    assert asker.questions[0][1] == ["Allow once", "Allow for this run", "Deny"]
    assert result.status == TaskStatus.COMPLETED


async def test_worker_fails_without_evidence_and_on_failed_runs(tmp_path):
    worker, _, _ = _worker(tmp_path, [{"event": "run.completed", "output": "guess", "seq": 0}])
    result = await worker.execute(TASK, "p", [_spec("read_file", ["file_reading"])])
    assert result.status == TaskStatus.FAILED and result.error.startswith("No evidence collected")
    assert len(worker.client.created) == 2  # one steering follow-up before giving up

    worker, _, _ = _worker(tmp_path, [{"event": "run.failed", "error": "model down", "seq": 0}])
    result = await worker.execute(TASK, "p", [])
    assert result.status == TaskStatus.FAILED and "model down" in result.error


async def test_worker_steers_a_toolless_answer_in_the_same_session(tmp_path):
    worker, client, _ = _worker(tmp_path, [])
    runs = iter([[{"event": "run.completed", "output": "guess", "seq": 0}],
                 [{"event": "tool.completed", "tool": "mcp__aiagent__read_file", "seq": 0},
                  {"event": "run.completed", "output": "grounded", "seq": 1}]])

    async def events(profile, key, run_id, last_seq=-1):
        for event in next(runs):
            yield event

    client.events = events
    result = await worker.execute(TASK, "p", [_spec("read_file", ["file_reading"])])
    assert result.status == TaskStatus.COMPLETED and result.output == "grounded"
    assert result.tool_calls_made == ["read_file"]
    first, steer = client.created
    assert steer["session_id"] == first["session_id"] and "mcp__aiagent__read_file" in steer["input"]


async def test_worker_input_names_task_tools_and_caps_prior_outputs(tmp_path):
    events = [{"event": "tool.completed", "tool": "mcp__aiagent__read_file", "seq": 0},
              {"event": "run.completed", "output": "ok", "seq": 1}]
    worker, client, _ = _worker(tmp_path, events)
    worker.settings.worker_max_context_chars = 500
    await worker.execute(TASK, "p", [_spec("read_file", ["file_reading"])], upstream_context={"t0": "x" * 5000})
    sent = client.created[0]["input"]
    assert "# Tools for This Task\nmcp__aiagent__read_file" in sent
    assert "Parameters:" not in sent  # Hermes already sends the full tool schemas
    assert sent.count("x") < 1000 and "[...truncated]" in sent


async def test_worker_continues_the_reviewed_session_on_supervisor_retry(tmp_path):
    worker, client, _ = _worker(tmp_path, [{"event": "run.completed", "output": "full answer", "seq": 0}])
    result = await worker.execute(TASK, "p", [_spec("read_file", ["file_reading"])],
                                  continue_session="sess-1", review_feedback="windows_endpoint.xml not covered")
    assert result.status == TaskStatus.COMPLETED and result.output == "full answer"
    assert result.hermes_session_id == "sess-1"
    assert len(client.created) == 1  # no "use a tool" follow-up: the session already holds the evidence
    sent = client.created[0]
    assert sent["session_id"] == "sess-1"
    assert "windows_endpoint.xml not covered" in sent["input"] and "Scan logs" not in sent["input"]


async def test_worker_stops_the_hermes_run_when_cancelled(tmp_path):
    import asyncio

    worker, client, _ = _worker(tmp_path, [])

    async def hang(profile, key, run_id, last_seq=-1):
        await asyncio.Event().wait()
        yield {}

    client.events = hang
    running = asyncio.create_task(worker.execute(TASK, "p", []))
    for _ in range(200):
        if client.created:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert client.stopped == ["run_1"]


async def test_worker_runs_fresh_when_the_reviewed_session_belongs_to_another_profile(tmp_path):
    worker, client, _ = _worker(tmp_path, [{"event": "tool.completed", "tool": "mcp__aiagent__read_file", "seq": 0},
                                           {"event": "run.completed", "output": "ok", "seq": 1}])
    await worker.execute(TASK, "p", [_spec("read_file", ["file_reading"])], continue_session="sess-1",
                         review_feedback="gaps", continue_profile="aiagent-bundle-files")
    sent = client.created[0]
    assert sent["session_id"] != "sess-1" and "Scan logs" in sent["input"]  # the default profile has no such session


async def test_worker_retries_inference_server_errors_with_a_fresh_run(tmp_path):
    peg = ('Engine protocol predict stream returned an error: {"code":500,"message":"The model produced output '
           'that does not match the expected peg-native format","type":"server_error"}')
    worker, client, _ = _worker(tmp_path, [])
    runs = iter([[{"event": "run.failed", "error": peg, "seq": 0}],
                 [{"event": "run.completed", "output": "ok", "seq": 0}]])

    async def events(profile, key, run_id, last_seq=-1):
        for event in next(runs):
            yield event

    client.events = events
    result = await worker.execute(TASK, "p", [])
    assert result.status == TaskStatus.COMPLETED and result.output == "ok" and len(client.created) == 2

    worker, client, _ = _worker(tmp_path, [{"event": "run.failed", "error": peg, "seq": 0}])
    result = await worker.execute(TASK, "p", [])
    assert result.status == TaskStatus.FAILED and "peg-native" in result.error and len(client.created) == 3


async def test_worker_reads_final_status_when_stream_ends_early(tmp_path):
    worker, _, _ = _worker(tmp_path, [], final={"status": "completed", "output": "from status"})
    result = await worker.execute(TASK, "p", [])
    assert result.output == "from status"


def test_mcp_connected_tracks_listing_after_configuration(tmp_path):
    state = ProfileState(tmp_path / "profiles.json")
    state.update("aiagent-soc", {"configured_at": 100.0})
    assert not state.mcp_connected("aiagent-soc")
    state.update("aiagent-soc", {"mcp_listed_at": 150.0})
    assert state.mcp_connected("aiagent-soc")
    state.mark_endpoint_started()  # aiagent restarted after that listing
    assert not state.mcp_connected("aiagent-soc")
    state.update("aiagent-soc", {"mcp_listed_at": time.time() + 1})
    assert state.mcp_connected("aiagent-soc")
    assert not state.mcp_connected("aiagent-soc", since=time.time() + 5)  # listed by the pre-restart gateway


async def test_worker_waits_for_hermes_to_reconnect_before_restarting(tmp_path, monkeypatch):
    import src.workers.hermes_agent_worker as hw

    hw._gateway_restarted_at = float("-inf")
    monkeypatch.setattr(hw, "CONFIG_PICKUP_SECONDS", 5)
    profiles = FakeProfiles(connected=False, changed=False)
    checks = iter([False, False, True])
    profiles.state = SimpleNamespace(mcp_connected=lambda name, since=0.0: next(checks, True))
    monkeypatch.setattr(hw.asyncio, "sleep", _no_sleep)
    worker = HermesAgentWorker(_settings(), client=FakeClient([{"event": "run.completed", "output": "ok", "seq": 0}]),
                               profiles=profiles, active=ActiveRuns(tmp_path / "active"), ask=Asker("x"))
    result = await worker.execute(TASK, "p", [])
    assert profiles.restarts == 0 and result.status == TaskStatus.COMPLETED


async def test_worker_accepts_the_listing_the_new_gateway_makes_while_restarting(tmp_path, monkeypatch):
    import src.workers.hermes_agent_worker as hw

    hw._gateway_restarted_at = float("-inf")
    monkeypatch.setattr(hw, "CONFIG_PICKUP_SECONDS", 0)
    monkeypatch.setattr(hw, "MCP_READY_TIMEOUT_SECONDS", 1)
    state = ProfileState(tmp_path / "profiles.json")
    state.update("aiagent-default", {"configured_at": 1.0})
    profiles = FakeProfiles(changed=False)
    profiles.state = state

    def restart_gateway():
        profiles.restarts += 1
        state.update("aiagent-default", {"mcp_listed_at": time.time()})  # startup discovery, before the CLI returns

    profiles.restart_gateway = restart_gateway
    worker = HermesAgentWorker(_settings(), client=FakeClient([{"event": "run.completed", "output": "ok", "seq": 0}]),
                               profiles=profiles, active=ActiveRuns(tmp_path / "active"), ask=Asker("x"))
    result = await worker.execute(TASK, "p", [])
    assert profiles.restarts == 1 and result.status == TaskStatus.COMPLETED


async def test_worker_restarts_gateway_when_listing_predates_aiagent_start(tmp_path, monkeypatch):
    import src.workers.hermes_agent_worker as hw

    hw._gateway_restarted_at = float("-inf")
    monkeypatch.setattr(hw, "CONFIG_PICKUP_SECONDS", 0)
    profiles = FakeProfiles(connected=False, changed=False)
    client = FakeClient([{"event": "run.completed", "output": "ok", "seq": 0}])
    worker = HermesAgentWorker(_settings(), client=client,
                               profiles=profiles, active=ActiveRuns(tmp_path / "active"), ask=Asker("x"))
    result = await worker.execute(TASK, "p", [])
    assert profiles.restarts == 1 and result.status == TaskStatus.COMPLETED
    assert client.health_checks >= 1  # waited for the restarted gateway's API before creating the run


async def test_worker_restarts_gateway_when_a_new_profile_is_not_picked_up(tmp_path, monkeypatch):
    import src.workers.hermes_agent_worker as hw

    hw._gateway_restarted_at = float("-inf")
    monkeypatch.setattr(hw, "CONFIG_PICKUP_SECONDS", 0)
    profiles = FakeProfiles(connected=False, changed=True)
    worker = HermesAgentWorker(_settings(), client=FakeClient([{"event": "run.completed", "output": "ok", "seq": 0}]),
                               profiles=profiles, active=ActiveRuns(tmp_path / "active"), ask=Asker("x"))
    result = await worker.execute(TASK, "p", [])
    assert profiles.restarts == 1 and result.status == TaskStatus.COMPLETED


async def test_list_tools_marks_the_profile_connected(registry, store, tmp_path):
    from src.hermes.mcp_server import build_server

    gate, _, _ = _gate(registry, store, tmp_path)
    gate.state.update("aiagent-soc", {"configured_at": 1.0})
    server = build_server(gate)
    handler = server.request_handlers[__import__("mcp.types", fromlist=["ListToolsRequest"]).ListToolsRequest]
    request = SimpleNamespace(scope={"aiagent_profile": SOC})
    from mcp.shared.context import RequestContext
    from mcp.server.lowlevel.server import request_ctx

    token = request_ctx.set(RequestContext(request_id=1, meta=None, session=None, lifespan_context=None,
                                           request=request))
    try:
        await handler(__import__("mcp.types", fromlist=["ListToolsRequest"]).ListToolsRequest(method="tools/list"))
    finally:
        request_ctx.reset(token)
    assert gate.state.mcp_connected("aiagent-soc")

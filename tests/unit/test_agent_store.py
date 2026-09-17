"""
Unit tests for AgentStore and AgentProfile persistence.
"""

import pytest
from pathlib import Path
from src.core.agent_models import AgentProfile
from src.core.agent_store import AgentStore
from src.core.models import RiskLevel, Task
from src.persona.synthesizer import PersonaSynthesizer
from src.registry.tool_registry import ToolSpec


@pytest.fixture
def temp_store(tmp_path: Path):
    return AgentStore(storage_dir=tmp_path / "agents")


def test_generate_id():
    assert AgentStore.generate_id("Security Analyst") == "security-analyst"
    assert AgentStore.generate_id("  DevOps & SRE Specialist!!  ") == "devops-sre-specialist"
    assert AgentStore.generate_id("123__Code_Reviewer") == "123-code-reviewer"
    assert AgentStore.generate_id("") == "custom-agent"


def test_save_and_load(temp_store: AgentStore):
    profile = AgentProfile(
        id="qa-engineer",
        name="QA Automation Engineer",
        description="Designs and runs integration tests",
        icon="🧪",
        system_prompt_template="You are a QA Engineer testing {task_name}.",
        curated_skills=["code_execution", "web_search"],
        tags=["qa", "testing"],
    )

    saved = temp_store.save(profile)
    assert saved.id == "qa-engineer"

    loaded = temp_store.load("qa-engineer")
    assert loaded is not None
    assert loaded.id == "qa-engineer"
    assert loaded.name == "QA Automation Engineer"
    assert loaded.icon == "🧪"
    assert loaded.curated_skills == ["code_execution", "web_search"]
    assert loaded.tags == ["qa", "testing"]
    assert loaded.system_prompt_template == "You are a QA Engineer testing {task_name}."


def test_list_all(temp_store: AgentStore):
    p1 = AgentProfile(
        id="agent-b",
        name="Beta Agent",
        description="Second agent",
    )
    p2 = AgentProfile(
        id="agent-a",
        name="Alpha Agent",
        description="First agent",
    )

    temp_store.save(p1)
    temp_store.save(p2)

    all_agents = temp_store.list_all()
    assert len(all_agents) == 2
    # Sorted by name
    assert all_agents[0].name == "Alpha Agent"
    assert all_agents[1].name == "Beta Agent"


def test_delete(temp_store: AgentStore):
    profile = AgentProfile(
        id="to-delete",
        name="Temporary Agent",
        description="Soon gone",
    )
    temp_store.save(profile)
    assert temp_store.load("to-delete") is not None

    deleted = temp_store.delete("to-delete")
    assert deleted is True
    assert temp_store.load("to-delete") is None

    # Deleting again returns False
    assert temp_store.delete("to-delete") is False


def test_synthesize_from_profile_with_template():
    synth = PersonaSynthesizer()
    profile = AgentProfile(
        id="custom-sec",
        name="Custom Security Agent",
        description="Security analysis agent",
        system_prompt_template="[CUSTOM PROMPT]\nTask: {task_name}\nDesc: {task_description}\nTools:\n{tools}",
    )
    task = Task(
        id="t1",
        name="Audit Auth Flow",
        description="Check JWT handling",
        required_skills=[],
        expected_output="Security findings",
    )
    prompt = synth.synthesize_from_profile(profile, task, tools=[])
    assert "[CUSTOM PROMPT]" in prompt
    assert "Audit Auth Flow" in prompt
    assert "Check JWT handling" in prompt
    assert "FINAL_ANSWER:" in prompt  # Injected safety


def test_synthesize_from_profile_fallback():
    synth = PersonaSynthesizer()
    profile = AgentProfile(
        id="custom-data",
        name="Data Scientist Agent",
        description="Expert in statistical modelling and forecasting.",
        system_prompt_template="",
    )
    task = Task(
        id="t2",
        name="Forecast Revenue",
        description="Calculate Q4 revenue forecast",
        required_skills=[],
        expected_output="Forecast table",
    )
    prompt = synth.synthesize_from_profile(profile, task, tools=[])
    assert "Your Role: Data Scientist Agent" in prompt
    assert "Expert in statistical modelling and forecasting." in prompt
    assert "Forecast Revenue" in prompt

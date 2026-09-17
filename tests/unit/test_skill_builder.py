"""
Unit tests for SkillBuilder: Python tool compilation, validation, registration,
and LLM response parsing.
"""

from pathlib import Path
from unittest.mock import AsyncMock
import pytest

from src.brain.skill_builder import SkillBuilder
from src.core.llm_client import LocalLLMClient
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolRegistry, ToolSpec


@pytest.fixture
def mock_llm():
    llm = LocalLLMClient(base_url="http://mock:1234/v1")
    llm.chat = AsyncMock()
    return llm


@pytest.fixture
def temp_builder(tmp_path: Path, mock_llm: LocalLLMClient):
    return SkillBuilder(llm=mock_llm, custom_tools_dir=tmp_path / "custom_tools")


def test_register_generated_tool_valid(temp_builder: SkillBuilder):
    registry = ToolRegistry()
    code = """
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

async def check_ssl(domain: str) -> str:
    return f"SSL valid for {domain}"

CHECK_SSL_SPEC = ToolSpec(
    tool_id="check_ssl_v1",
    name="check_ssl",
    description="Validates SSL certificate",
    skills_provided=["ssl_check"],
    parameters={
        "domain": {"type": "string", "description": "Target domain", "required": True}
    },
    function=check_ssl,
    risk_level=RiskLevel.LOW,
)
"""
    spec = temp_builder.register_generated_tool(
        tool_code=code,
        tool_name="check_ssl",
        registry=registry,
        persist=True,
    )

    assert spec.name == "check_ssl"
    assert "ssl_check" in spec.skills_provided
    assert registry.has_tool("check_ssl")

    # Verify persisted file
    persisted_file = temp_builder.custom_tools_dir / "check_ssl.py"
    assert persisted_file.exists()
    assert "def check_ssl" in persisted_file.read_text(encoding="utf-8")


def test_register_generated_tool_syntax_error(temp_builder: SkillBuilder):
    registry = ToolRegistry()
    bad_code = "def broken(::"
    with pytest.raises(ValueError, match="syntax errors"):
        temp_builder.register_generated_tool(bad_code, "broken", registry)


def test_register_generated_tool_missing_spec(temp_builder: SkillBuilder):
    registry = ToolRegistry()
    code = "def some_func(): return 123"
    with pytest.raises(ValueError, match="No ToolSpec"):
        temp_builder.register_generated_tool(code, "some_func", registry)


def test_extract_json(temp_builder: SkillBuilder):
    raw_markdown = """Here is your tool:
```json
{
  "tool_name": "calc_tax",
  "tool_code": "code",
  "skill_names": ["finance"],
  "risk_level": "low",
  "explanation": "Calculates sales tax"
}
```
Hope this helps!"""
    data = temp_builder._extract_json(raw_markdown)
    assert data["tool_name"] == "calc_tax"
    assert data["risk_level"] == "low"


@pytest.mark.asyncio
async def test_generate_tool_flow(temp_builder: SkillBuilder, mock_llm: LocalLLMClient):
    mock_llm.chat.return_value = """
{
  "tool_name": "lookup_dns",
  "tool_code": "code",
  "skill_names": ["dns_lookup", "network"],
  "risk_level": "low",
  "explanation": "Queries DNS records"
}
"""
    resp = await temp_builder.generate_tool("Query DNS records", "lookup_dns", ["web_search"])
    assert resp.tool_name == "lookup_dns"
    assert "dns_lookup" in resp.skill_names
    assert resp.risk_level == "low"
    assert resp.explanation == "Queries DNS records"


@pytest.mark.asyncio
async def test_generate_agent_profile_flow(temp_builder: SkillBuilder, mock_llm: LocalLLMClient):
    mock_llm.chat.return_value = """
{
  "suggested_name": "Network Ops Specialist",
  "suggested_description": "Monitors network reliability and DNS",
  "suggested_icon": "🌐",
  "suggested_system_prompt_template": "You are a network specialist.",
  "suggested_skills": ["web_search", "code_execution"],
  "suggested_tags": ["network", "ops"]
}
"""
    resp = await temp_builder.generate_agent_profile(
        "Agent for network troubleshooting",
        ["web_search", "code_execution", "file_reading"],
    )
    assert resp.suggested_name == "Network Ops Specialist"
    assert resp.suggested_icon == "🌐"
    assert "network" in resp.suggested_tags

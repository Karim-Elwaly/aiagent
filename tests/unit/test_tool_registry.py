"""
Unit tests for UAOS ToolRegistry and Auto-Discovery
"""

import pytest

from src.core.models import RiskLevel
from src.registry.auto_discover import register_all_tools
from src.registry.tool_registry import ToolRegistry, ToolSpec


async def dummy_fn(x: int = 1) -> int:
    """A dummy async tool function."""
    return x * 2


@pytest.fixture
def registry():
    return ToolRegistry()


@pytest.mark.asyncio
async def test_register_and_get_tool(registry):
    spec = ToolSpec(
        tool_id="test_math",
        name="multiply_two",
        description="Multiplies number by 2",
        skills_provided=["math", "calculation"],
        parameters={"x": {"type": "integer", "description": "Input number", "required": True}},
        risk_level=RiskLevel.LOW,
        function=dummy_fn,
    )
    registry.register(spec)

    assert registry.tool_count == 1
    assert registry.skill_count == 2
    retrieved = registry.get_tool("test_math")
    assert retrieved is not None
    assert retrieved.name == "multiply_two"
    assert await retrieved.function(3) == 6


def test_resolve_skills(registry):
    async def search_fn(q: str) -> str:
        return f"result: {q}"

    spec1 = ToolSpec(
        tool_id="search_tool",
        name="web_search",
        description="Searches web",
        skills_provided=["web_search", "research"],
        parameters={"q": {"type": "string"}},
        function=search_fn,
    )
    spec2 = ToolSpec(
        tool_id="calc_tool",
        name="calc",
        description="Calculates",
        skills_provided=["math", "calculation"],
        parameters={},
        function=dummy_fn,
    )
    registry.register(spec1)
    registry.register(spec2)

    tools = registry.resolve(["web_search"])
    assert len(tools) == 1
    assert tools[0].tool_id == "search_tool"

    # Multi-skill resolution with deduplication
    tools_multi = registry.resolve(["research", "math", "web_search"])
    assert len(tools_multi) == 2
    ids = {t.tool_id for t in tools_multi}
    assert ids == {"search_tool", "calc_tool"}


def test_get_unknown_tool(registry):
    assert registry.get_tool("nonexistent") is None


def test_auto_discovery():
    reg = ToolRegistry()
    count = register_all_tools(reg)
    assert count > 0

    # Starter tools should be auto-discovered
    assert reg.get_tool("file_reader_v1") is not None
    assert reg.get_tool("python_executor_v1") is not None
    assert reg.get_tool("web_search_v1") is not None

    skills = reg.list_skills()
    assert len(skills) > 0
    assert "web_search" in skills
    assert "file_reading" in skills
    assert "code_execution" in skills


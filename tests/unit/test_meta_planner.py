"""
Unit tests for MetaPlanner: task decomposition, retry, JSON extraction, and fallback.
"""

from unittest.mock import AsyncMock

import pytest

from src.brain.meta_planner import MetaPlanner
from src.core.exceptions import JSONParseError
from src.core.llm_client import LocalLLMClient


@pytest.fixture
def mock_llm():
    llm = AsyncMock(spec=LocalLLMClient)
    return llm


@pytest.fixture
def planner(mock_llm):
    return MetaPlanner(
        llm=mock_llm,
        available_skills=["web_search", "code_execution", "file_read"],
        max_retries=2,
    )


@pytest.mark.asyncio
async def test_plan_successful_json(planner, mock_llm):
    valid_json = """{
        "goal": "Analyze cybersecurity alert",
        "reasoning": "Need to check logs and then correlate",
        "tasks": [
            {
                "id": "t1",
                "name": "Fetch logs",
                "description": "Read security log file",
                "required_skills": ["file_read"],
                "dependencies": [],
                "expected_output": "Log entries"
            },
            {
                "id": "t2",
                "name": "Analyze anomalies",
                "description": "Run Python analysis on fetched logs",
                "required_skills": ["code_execution"],
                "dependencies": ["t1"],
                "expected_output": "Anomalies report"
            }
        ]
    }"""
    mock_llm.chat.return_value = valid_json

    dag = await planner.plan("Check logs and analyze anomalies")
    assert dag.goal == "Analyze cybersecurity alert"
    assert len(dag.tasks) == 2
    assert dag.tasks[0].id == "t1"
    assert dag.tasks[1].dependencies == ["t1"]


@pytest.mark.asyncio
async def test_plan_with_markdown_blocks(planner, mock_llm):
    wrapped_json = """Here is the plan:
```json
{
    "goal": "Search and summarize",
    "reasoning": "Sequential search then summarize",
    "tasks": [
        {
            "id": "t1",
            "name": "Search",
            "description": "Search web",
            "required_skills": ["web_search"],
            "dependencies": [],
            "expected_output": "Search findings"
        }
    ]
}
```
Hope this helps!"""
    mock_llm.chat.return_value = wrapped_json

    dag = await planner.plan("Search web")
    assert len(dag.tasks) == 1
    assert dag.tasks[0].name == "Search"


@pytest.mark.asyncio
async def test_plan_retry_on_invalid_json(planner, mock_llm):
    # First response invalid, second response valid
    valid_json = """{
        "goal": "Test goal",
        "reasoning": "Simple task",
        "tasks": [
            {
                "id": "t1",
                "name": "Task 1",
                "description": "Run task",
                "required_skills": [],
                "dependencies": [],
                "expected_output": "Done"
            }
        ]
    }"""
    mock_llm.chat.side_effect = ["Invalid json string {..", valid_json]

    dag = await planner.plan("Test prompt")
    assert mock_llm.chat.call_count == 2
    assert len(dag.tasks) == 1


@pytest.mark.asyncio
async def test_plan_fallback_on_all_failures(planner, mock_llm):
    mock_llm.chat.return_value = "Non-json text every time"

    dag = await planner.plan("Do something impossible to parse")
    assert len(dag.tasks) == 1
    assert dag.tasks[0].id == "t1"
    assert "Direct Execution" in dag.tasks[0].name
    assert "fallback" in dag.reasoning.lower()


def test_extract_json_variants(planner):
    # Pure JSON
    assert planner._extract_json('{"key": "value"}') == '{"key": "value"}'

    # Wrapped in markdown
    assert (
        planner._extract_json('Text\n```json\n{"key": "value"}\n```')
        == '{"key": "value"}'
    )

    # Surrounded by text without markdown
    assert (
        planner._extract_json('Result is: {"key": "value"} and more')
        == '{"key": "value"}'
    )

    # Invalid raises JSONParseError
    with pytest.raises(JSONParseError):
        planner._extract_json("no json here at all")

"""
Unit tests for Hermes Skill Adapter and Loader.
"""

from pathlib import Path
import pytest

from src.registry.hermes.hermes_adapter import (
    derive_skills,
    determine_risk_level,
    hermes_skill_to_tool_spec,
    parse_skill_markdown,
)
from src.registry.hermes.hermes_loader import (
    import_and_persist_hermes_skill,
    list_hermes_skills_catalog,
)
from src.registry.tool_registry import ToolRegistry
from src.core.models import RiskLevel


SAMPLE_SKILL_MD = """---
name: airtable_crud
description: Airtable REST API via curl. Records CRUD, filters, upserts.
version: 1.1.0
author: hermes_community
license: MIT
metadata:
  category: productivity
  skills: [airtable, database, records]
  risk_level: low
parameters:
  action:
    type: string
    description: Action to perform (get, list, create, update, delete)
    required: true
  table:
    type: string
    description: Airtable table name
    required: true
---

# Airtable Skill
Use this skill to interact with Airtable records.
"""


def test_parse_skill_markdown():
    metadata, instructions = parse_skill_markdown(SAMPLE_SKILL_MD)
    assert metadata["name"] == "airtable_crud"
    assert "Airtable REST API" in metadata["description"]
    assert "Airtable Skill" in instructions


def test_hermes_skill_to_tool_spec():
    spec = hermes_skill_to_tool_spec(SAMPLE_SKILL_MD)
    assert spec.name == "airtable_crud"
    assert spec.tool_id == "hermes_airtable_crud_v1"
    assert "airtable" in spec.skills_provided
    assert "records" in spec.skills_provided
    assert "action" in spec.parameters
    assert spec.risk_level == RiskLevel.LOW
    assert spec.source_type == "hermes"


def test_determine_risk_level():
    assert determine_risk_level("delete_user_data", "Permanently delete user") == RiskLevel.CRITICAL
    assert determine_risk_level("read_logs", "Read only system logs") == RiskLevel.LOW
    assert determine_risk_level("write_file", "Write content to disk") == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_hermes_tool_execution():
    spec = hermes_skill_to_tool_spec(SAMPLE_SKILL_MD)
    registry = ToolRegistry()
    registry.register(spec)
    assert registry.has_tool("airtable_crud")

    result = await spec.function(action="list", table="Tasks")
    assert "Executed Hermes Skill: airtable_crud" in result
    assert "action: list" in result
    assert "table: Tasks" in result


def test_import_and_persist(tmp_path: Path, monkeypatch):
    import src.registry.hermes.hermes_loader as loader_mod

    monkeypatch.setattr(loader_mod, "HERMES_SKILLS_DIR", tmp_path / "hermes_skills")
    registry = ToolRegistry()
    spec = import_and_persist_hermes_skill(SAMPLE_SKILL_MD, registry=registry, persist=True)

    assert registry.has_tool(spec.name)
    saved_file = tmp_path / "hermes_skills" / f"{spec.name}.md"
    assert saved_file.exists()

    catalog = list_hermes_skills_catalog()
    assert len(catalog) == 1
    assert catalog[0]["name"] == "airtable_crud"

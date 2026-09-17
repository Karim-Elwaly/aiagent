"""
UAOS Agent & Skill Models

Defines data structures for reusable Agent Profiles and AI-generated Skills.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentProfile(BaseModel):
    """A reusable, persisted agent configuration."""

    id: str = Field(description="Unique slug identifier, e.g. 'security-analyst'")
    name: str = Field(description="Human-readable agent name")
    description: str = Field(description="Purpose and specialty of this agent")
    icon: str = Field(default="🤖", description="Emoji or icon representative for the agent")
    system_prompt_template: str = Field(
        default="",
        description="Custom persona prompt template. Placeholders: {task_name}, {task_description}, {tools}, {expected_output}",
    )
    curated_skills: list[str] = Field(
        default_factory=list,
        description="Allowed abstract skill names. Empty list means all available skills are accessible.",
    )
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Creation timestamp (ISO 8601)",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Last updated timestamp (ISO 8601)",
    )


class AgentCreateRequest(BaseModel):
    """Request payload to create a new agent."""

    name: str
    description: str
    icon: str = "🤖"
    system_prompt_template: str = ""
    curated_skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AgentUpdateRequest(BaseModel):
    """Request payload to update an existing agent."""

    name: str | None = None
    description: str | None = None
    icon: str | None = None
    system_prompt_template: str | None = None
    curated_skills: list[str] | None = None
    tags: list[str] | None = None


class AgentGenerateRequest(BaseModel):
    """Request to use LLM to design an agent from natural language."""

    description: str = Field(description="Natural language description of what this agent should do")


class AgentGenerateResponse(BaseModel):
    """LLM-suggested configuration for an agent."""

    suggested_name: str
    suggested_description: str
    suggested_icon: str = "🤖"
    suggested_system_prompt_template: str = ""
    suggested_skills: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)


class SkillGenerateRequest(BaseModel):
    """Request to generate Python tool code from a natural language prompt."""

    description: str = Field(description="Natural language description of the tool to build")
    suggested_name: str = Field(default="", description="Optional name hint for the tool function")


class SkillGenerateResponse(BaseModel):
    """Generated Python tool code ready for admin review."""

    tool_name: str
    tool_code: str
    skill_names: list[str] = Field(default_factory=list)
    risk_level: str = "medium"
    explanation: str = ""


class SkillRegisterRequest(BaseModel):
    """Payload to confirm and persist a generated skill tool."""

    tool_name: str
    tool_code: str
    skill_names: list[str] = Field(default_factory=list)
    risk_level: str = "medium"
    description: str = ""


class HermesSkillImportPayload(BaseModel):
    """Payload to import a Hermes-style SKILL.md or JSON skill into UAOS."""

    content: str = Field(description="Raw SKILL.md markdown or JSON content")
    name_override: str | None = Field(default=None, description="Optional name override")
    persist: bool = Field(default=True, description="Persist to data/hermes_skills/")

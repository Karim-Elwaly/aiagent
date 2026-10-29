"""
UAOS Persona Synthesizer

Generates dynamic system prompts that transform blank-slate Universal
Worker Agents into domain specialists. Critical for local LLMs — strong
persona steering dramatically improves tool usage and output quality.

The synthesizer handles:
  - Tool description formatting for the worker prompt
  - Upstream context injection with size capping (prevents window overflow)
  - Clear instruction structure for reliable ReAct loop behavior
"""

from __future__ import annotations

import json
import logging

from src.core.agent_models import AgentProfile
from src.core.models import Task
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

HERMES_PROTOCOL_BLOCK = """# Tool Use
You run inside Hermes Agent. Your assigned tools appear as function calls starting with mcp__aiagent__; this section overrides any earlier tool-call format instructions.
1. Always execute your tools FIRST via native function calls to gather real data from the local host (D:, C:). The tools run directly on the host with full filesystem and network visibility; NEVER claim lack of access or lack of file-reading capability.
2. Directly invoke tools by their native names (e.g. mcp__aiagent__gather_log_evidence, mcp__aiagent__triage_security_alert, mcp__aiagent__extract_threat_indicators, mcp__aiagent__analyze_incident_impact, mcp__aiagent__compress_security_timeline, mcp__aiagent__propose_containment_response, mcp__aiagent__read_file, mcp__aiagent__list_directory).
3. DO NOT call skill_view, skill_manage, or browse skills for mcp__aiagent__ tools. They are already provided directly to you as active callable tools.
4. DO NOT just draft or output the function call syntax as text or markdown. You MUST actually trigger the function call so the system executes it.
5. After each tool result, analyze the returned data and decide whether another tool call is needed.
6. When you have collected the required evidence, reply with your comprehensive final answer incorporating all findings, metrics, and indicators from the tool results.
7. If the task cannot be completed with available tools, explain specifically what is missing."""


class PersonaSynthesizer:
    """Generates focused system prompts for Universal Worker Agents.

    Every worker is born as a blank slate. The persona prompt is what
    makes it behave as a "Security Analyst" vs a "Data Scientist" vs
    a "Technical Writer". This steering is especially important for
    local LLMs that benefit from strong role-setting.
    """

    def __init__(self, max_context_chars: int = 3000):
        """
        Args:
            max_context_chars: Maximum characters of upstream context
                to include in the prompt. Prevents context window overflow
                for models with small windows (8K). Increase for 32K+ models.
        """
        self.max_context_chars = max_context_chars

    def synthesize(
        self,
        task: Task,
        tools: list[ToolSpec],
        upstream_context: dict[str, str] | None = None,
        tool_call_mode: str | None = None,
        protocol: str = "legacy",
    ) -> str:
        """Generate a complete system prompt for a worker agent.

        Args:
            task: The task to execute.
            tools: Resolved concrete tools from the ToolRegistry.
            upstream_context: {task_id: output} from completed dependencies.
            tool_call_mode: Optional 'native' | 'tags' | 'legacy'. If None, reads from settings.
            protocol: "legacy" (JSON ReAct) or "hermes" (function calling).

        Returns:
            A system prompt string ready to be injected as the worker's
            system message.
        """
        if protocol == "hermes":
            return self._synthesize_hermes(
                "# Your Role\nYou are a worker agent executing ONE task on the host machine using available tools."
            )
        from src.core.config import get_settings
        mode = tool_call_mode or getattr(get_settings(), "tool_call_mode", "legacy")

        context_block = self._format_upstream_context(
            upstream_context or {}
        )

        if not tools:
            return f"""# Your Role
You are a Lead Domain Specialist, Executive Strategist, and Content Creator.

# Your Task
**{task.name}**
{task.description}

# Expected Output
{task.expected_output}

# Workflow & Core Directives
1. Deliver the COMPLETE, finished deliverable requested directly.
2. When asked to write, design, draft, or plan (e.g. pitch decks, business strategy, architecture, reports, or outlines):
   - Write out the complete, exhaustive content in full detail with no placeholders.
   - Provide realistic, industry-standard projections, market figures, structured tables, and compelling narratives.
   - Never output refusals, data collection checklists, or claim missing information when asked to create or draft.
3. Format with clean GitHub-flavored Markdown: clear headers, structured tables, bullet points, and speaker notes.
4. Conclude with your complete deliverable under:
FINAL_ANSWER: <your complete, well-structured deliverable>
{context_block}"""

        if mode == "tags":
            from src.core.tool_call_parser import format_tools_to_hermes_xml
            tool_format_instruction = (
                "You have access to tools via Hermes XML syntax.\n"
                f"{format_tools_to_hermes_xml(tools)}"
            )
        elif mode == "native":
            tool_format_instruction = (
                "# Available Tools\n"
                "You have access to native tools declared in this conversation. "
                "Call tools whenever needed to inspect targets or gather data."
            )
        else:
            tool_block = self._format_tools(tools)
            tool_format_instruction = f"""# Available Tools
Tool call format:
{{"tool": "<tool_name>", "args": {{"param1": "value1"}}}}

{tool_block}"""

        return f"""# Your Role
You are a worker agent executing ONE task on the host machine using available tools.

# Your Task
**{task.name}**
{task.description}

# Expected Output
{task.expected_output}

{tool_format_instruction}

# Workflow & Rules
1. Always call tools first to inspect real paths and compute data.
2. Host environment with direct filesystem/drive access (C:, D:). Never claim lack of access.
3. When done, output: FINAL_ANSWER: <complete findings, table, and data>.
4. If truly impossible with tools, output: CANNOT_COMPLETE: <reason>.
5. Never return an empty FINAL_ANSWER. Always include tool results.
6. Do NOT invent tools. Only use tools listed above.
{context_block}"""

    def synthesize_from_profile(
        self,
        profile: AgentProfile,
        task: Task,
        tools: list[ToolSpec],
        upstream_context: dict[str, str] | None = None,
        protocol: str = "legacy",
    ) -> str:
        """Generate a custom persona prompt based on an AgentProfile configuration.

        If the profile has a system_prompt_template, it fills placeholders:
        {task_name}, {task_description}, {expected_output}, {tools}.
        Otherwise, falls back to standard synthesis steered by the agent's role.
        """
        if protocol == "hermes":
            return self._synthesize_profile_hermes(profile)
        tool_block = self._format_tools(tools)
        context_block = self._format_upstream_context(upstream_context or {})

        if profile.system_prompt_template and profile.system_prompt_template.strip():
            template = profile.system_prompt_template
            prompt = (
                template.replace("{task_name}", task.name)
                .replace("{task_description}", task.description)
                .replace("{expected_output}", task.expected_output)
                .replace("{tools}", tool_block)
            )

            # Ensure tool call format and workflow rules are provided if omitted in template
            if "FINAL_ANSWER:" not in prompt:
                prompt += f"""

# Available Tools
When you need to use a tool, output a tool call in this EXACT JSON format on its own line:
{{"tool": "<tool_name>", "args": {{"param1": "value1", "param2": "value2"}}}}

{tool_block}

# Workflow
1. Think about what you need to do.
2. If you need information or need to perform an action, call a tool.
3. After receiving a tool result, analyze it and decide your next step.
4. You may call multiple tools sequentially.
5. When you have enough information to provide a complete answer, write:

FINAL_ANSWER: <your complete, well-structured response>

6. If you truly cannot complete the task with available tools, write:

CANNOT_COMPLETE: <specific explanation of what's missing>

# Rules
- Use tools proactively — don't guess when you can look up or compute.
- Be precise and structured — downstream tasks depend on your output.
- Do NOT invent tool names. Only use tools listed above.
- Do NOT call a tool and provide a FINAL_ANSWER in the same response.
"""
            if context_block and context_block not in prompt:
                prompt += f"\n{context_block}"
            return prompt

        # Fallback: standard synthesis steered by agent's custom persona name and description
        if not tools:
            return f"""# Your Role: {profile.name}
{profile.description}

You are operating as the specialized agent '{profile.name}'. Your entire focus is on delivering a comprehensive, authoritative solution for this task.

# Your Task
**{task.name}**
{task.description}

# Expected Output
{task.expected_output}

# Workflow & Guidelines
1. Deliver the COMPLETE, finished deliverable requested directly.
2. Provide rich, professional content with real-world frameworks, structured tables, and detailed actionable sections. Do NOT give placeholder refusals or demand missing data when asked to draft or create.
3. Conclude with your complete deliverable under:
FINAL_ANSWER: <your complete, well-structured deliverable>
{context_block}"""

        return f"""# Your Role: {profile.name}
{profile.description}

You are operating as the specialized agent '{profile.name}'. Your entire focus is on completing this task accurately within your domain specialty.

# Your Task
**{task.name}**

{task.description}

# Expected Output
{task.expected_output}

# Available Tools
When you need to use a tool, output a tool call in this EXACT JSON format on its own line:
{{"tool": "<tool_name>", "args": {{"param1": "value1", "param2": "value2"}}}}

{tool_block}

# Workflow
1. Think about what you need to do.
2. If you need information or need to perform an action, call a tool.
3. After receiving a tool result, analyze it and decide your next step.
4. You may call multiple tools sequentially.
5. When you have enough information to provide a complete answer, write:

FINAL_ANSWER: <your complete, well-structured response>

6. If you truly cannot complete the task with available tools, write:

CANNOT_COMPLETE: <specific explanation of what's missing>

# Rules
- Use tools proactively to gather concrete data from the environment.
- After receiving tool results, provide your full response under: FINAL_ANSWER: <complete findings, table, and data>.
- Never return an empty or blank FINAL_ANSWER. Always include the findings obtained from tools.
- Do NOT invent tool names. Only use tools listed above.
- Do NOT call a tool and provide a FINAL_ANSWER in the same response.
{context_block}"""

    def _synthesize_hermes(self, role_block: str) -> str:
        # Hermes runs get the task, tool names and prior outputs once, in the run input.
        return f"{role_block}\n\n{HERMES_PROTOCOL_BLOCK}"

    def _synthesize_profile_hermes(self, profile: AgentProfile) -> str:
        # The persona is the profile's SOUL.md, which Hermes loads as the agent's identity.
        return HERMES_PROTOCOL_BLOCK

    def _format_tools(self, tools: list[ToolSpec]) -> str:
        """Format tool descriptions for the worker prompt."""
        if not tools:
            return (
                "No tools available. Answer based on your knowledge only.\n"
                "Provide your response as: FINAL_ANSWER: <response>"
            )

        lines = []
        for t in tools:
            # Build parameter descriptions
            param_parts = []
            for pname, pinfo in t.parameters.items():
                ptype = pinfo.get("type", "any")
                pdesc = pinfo.get("description", "")
                preq = "required" if pinfo.get("required") else "optional"
                param_parts.append(f"  - **{pname}** ({ptype}, {preq}): {pdesc}")

            params_str = "\n".join(param_parts) if param_parts else "  (no parameters)"

            lines.append(
                f"## `{t.name}`\n"
                f"{t.description}\n"
                f"Parameters:\n{params_str}\n"
                f"Example: {{\"tool\": \"{t.name}\", \"args\": {self._example_args(t)}}}"
            )

        return "\n\n".join(lines)

    def _example_args(self, tool: ToolSpec) -> str:
        """Generate a realistic example args dict for the tool."""
        example = {}
        for pname, pinfo in tool.parameters.items():
            ptype = pinfo.get("type", "string")
            pname_lower = pname.lower()
            if "path" in pname_lower or "dir" in pname_lower or "folder" in pname_lower:
                example[pname] = "D:\\"
            elif "file" in pname_lower:
                example[pname] = "D:\\example.txt"
            elif "code" in pname_lower or "script" in pname_lower:
                example[pname] = "print('Hello')"
            elif "query" in pname_lower or "search" in pname_lower:
                example[pname] = "system metrics"
            elif "command" in pname_lower or "cmd" in pname_lower:
                example[pname] = "dir D:\\"
            elif ptype == "integer":
                example[pname] = 2
            elif ptype == "boolean":
                example[pname] = True
            else:
                example[pname] = "value"
        return json.dumps(example)

    def _format_upstream_context(
        self, upstream: dict[str, str], workflow_id: str | None = None
    ) -> str:
        return format_upstream_context(upstream, self.max_context_chars, workflow_id=workflow_id)


def format_upstream_context(
    upstream: dict[str, str],
    max_chars: int,
    workflow_id: str | None = None,
) -> str:
    """Format upstream task outputs losslessly by pairing executive extracts with artifact pointers."""
    if not upstream:
        return ""

    try:
        from src.core.artifact_exchange import WorkflowArtifactExchange
        exchange = WorkflowArtifactExchange(workflow_id) if workflow_id else None
    except Exception:
        exchange = None

    block = "\n# Context from Prior Tasks\n"
    block += (
        "The following verified data was produced by upstream tasks. "
        "Key excerpts are provided below, and complete lossless payloads are saved to disk.\n"
    )

    num_tasks = max(1, len(upstream))
    # Give each task an equitable allocation of the context budget, scaling with max_chars (capped at 1,500 chars)
    per_task_budget = max(100, min(1500, max_chars // num_tasks))

    for task_id, output in upstream.items():
        clean_output = (output or "").strip()
        pointer = exchange.get_artifact_pointer(task_id) if exchange else None

        pointer_note = ""
        if pointer and pointer.get("path"):
            pointer_note = (
                f"> **Lossless Artifact**: `{pointer['path']}` ({pointer['size_bytes']} bytes). "
                "For full data tables, exact values, or raw metrics, inspect this file directly.\n"
            )

        if len(clean_output) > per_task_budget:
            excerpt = clean_output[:per_task_budget].rstrip() + "\n[...truncated — see artifact on disk for full data]"
        else:
            excerpt = clean_output

        header_lines = [f"\n## From task `{task_id}`:"]
        if pointer_note:
            header_lines.append(pointer_note.strip())
        header_lines.append(excerpt)
        block += "\n".join(header_lines) + "\n"

    return block

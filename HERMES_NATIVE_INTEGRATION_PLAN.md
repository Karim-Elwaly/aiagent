# Implementation Plan: Hermes Native Tools & Skills Unleashed

## 1. Executive Summary

When running tasks directly in Hermes CLI or standalone API, Hermes operates autonomously with its **full suite of native toolsets** (`terminal`, `file`, `skills`, `code_execution`, `web`, etc.) and its complete library of native skills (including document extractors like `docx`, `pdf`, `git`, etc.). Tasks such as parsing a `.docx` request and creating a proposal complete rapidly and without error.

In contrast, when tasks are executed via **AgentHub → Hermes**, AgentHub currently acts as a **restrictive middleman** that disables Hermes's native strengths:
1. **Disables Hermes Native Toolsets**: Dynamic profiles (`aiagent-dyn-*`) deliberately strip all native toolsets (`wanted = set()`), running `hermes tools disable` for `terminal`, `file`, `skills`, `web`, `code_execution`, etc.
2. **Purges Native Hermes Skills**: `sync_exact_task_skills` deletes every skill except 1–3 AgentHub-selected skills, wiping out built-in Hermes skills like `docx`, `pdf`, `python`, etc.
3. **Restricts Tool Whitelists**: Forces Hermes's profile configuration to only include the few MCP tools that AgentHub's planner predicted.
4. **Adversarial Directives**: Instructs Hermes: *"Invoke `mcp__aiagent__<tool>` directly... Do NOT use skill_view... Do NOT produce conversational plans"*, actively penalizing Hermes if it tries to use its own skills.
5. **Fragile Proxies**: Forces Hermes to use AgentHub's `read_file` (which fails on binary files like `.docx`) instead of Hermes's native terminal/python docx parsers.

This implementation plan details how to transform AgentHub from a **constraining middleman** into a **strategic orchestrator**: AgentHub plans the high-level workflow DAG, tracks phase execution, and offers MCP tools as *enhancements*, while **leaving Hermes completely free to use its native toolsets, skills, and execution engine**.

---

## 2. Architectural Comparison

```
CURRENT MODEL (Restrictive Middleman)
┌────────────────────────────────────────────────────────┐
│ AgentHub Planner / Worker                              │
│   ├── Strips native toolsets in dynamic profiles       │
│   ├── Deletes non-matching Hermes skills from profile  │
│   ├── Restricts MCP whitelist to planner guesses       │
│   └── Injects anti-skill / anti-terminal directives   │
└───────────────────────────┬────────────────────────────┘
                            │ (Locked down)
                            ▼
┌────────────────────────────────────────────────────────┐
│ Hermes Agent                                           │
│   ✖ No Terminal or Bash                                │
│   ✖ No Native Skills (e.g. docx, git, python)          │
│   ✖ Forced to use AgentHub's mcp__aiagent__read_file   │
│   ✖ Crashes on .docx / binary files                    │
└────────────────────────────────────────────────────────┘

TARGET PRO MODEL (Strategic Orchestrator + Autonomous Hermes)
┌────────────────────────────────────────────────────────┐
│ AgentHub (Strategic Orchestrator)                      │
│   ├── High-level DAG decomposition & dependency state  │
│   ├── Real-time UI progress & event streaming          │
│   └── Exposes AgentHub custom MCP tools (as additions) │
└───────────────────────────┬────────────────────────────┘
                            │ (Unconstrained)
                            ▼
┌────────────────────────────────────────────────────────┐
│ Hermes Agent (Native Powerhouse)                       │
│   ✔ Native Toolsets Active (terminal, file, web, etc.) │
│   ✔ Full Skills Intact (~/.hermes/skills + docx/pdf)   │
│   ✔ Free to run python, inspect files, invoke skills   │
│   ✔ Can ALSO invoke AgentHub MCP tools when useful     │
└────────────────────────────────────────────────────────┘
```

---

## 3. The 5 Core Pillars

### Pillar 1: Unlocking Native Toolsets in Profiles
* **File**: `src/core/config.py` & `src/hermes/profiles.py`
* **Current Issue**: `wanted_toolsets()` in `profiles.py` sets `wanted = set(agent_toolsets or [])` for any profile starting with `aiagent-dyn-`. Because `agent_toolsets` is typically empty or None during dynamic task provisioning, `wanted` becomes empty. Then `apply_toolsets()` explicitly executes:
  `hermes -p <profile> tools disable --platform api_server terminal file web skills code_execution ...`
* **Changes**:
  1. Add configuration setting in `src/core/config.py`:
     ```python
     hermes_default_toolsets: list[str] = [
         "file", "terminal", "skills", "web", "code_execution"
     ]
     hermes_enable_native_toolsets: bool = True
     ```
  2. Update `wanted_toolsets()` in `src/hermes/profiles.py`:
     Dynamic profiles must inherit `settings.hermes_default_toolsets` and `REQUIRED_TOOLSETS`, ensuring Hermes has native terminal, file, and skill capabilities enabled on all task profiles.

### Pillar 2: Preserving the Hermes Skills Ecosystem
* **File**: `src/hermes/profiles.py` & `src/hermes/skills.py`
* **Current Issue**: In `sync_exact_task_skills()`, the code iterates over `p_skills.iterdir()` and removes any directory or file whose name is not in the planner's matched skills. This deletes native Hermes skills (`docx`, `pdf`, `git`, `python`, etc.) that were cloned or available in Hermes.
* **Changes**:
  1. Partition skill management: Only prune synthetic skills generated by AgentHub (names starting with `aiagent-`).
  2. Never delete native/community Hermes skills (such as `docx`, `pdf`, etc.) located in the profile's `skills/` directory.
  3. Ensure `skills.external_dirs` in profile configuration continues to reference the global Hermes skill repository (`~/.hermes/skills`) so Hermes can dynamically search and load any installed skill.

### Pillar 3: Eliminating Adversarial Directives in Worker Prompts
* **File**: `src/workers/hermes_agent_worker.py`
* **Current Issue**:
  `_user_content()`, `_steering_message()`, and `_review_message()` inject aggressive system instructions:
  - *"Immediate Action Required: Invoke {names} directly via native function calling."*
  - *"Do NOT produce conversational commentary, planning monologues, or text explanations before calling the tool."*
  - *"Do NOT use skill_view."*
  These directives actively punish Hermes for checking its skills or using scripts.
* **Changes**:
  1. Replace restrictive directives with collaborative instructions:
     *"You have full autonomous access to your native tools (terminal, file operations, python scripts, skills) as well as the specialized AgentHub MCP tools listed below. Choose the most effective tool or skill for the task."*
  2. Remove all bans against `skill_view`.
  3. Present AgentHub MCP tools as optional enhancements rather than mandatory funnels.

### Pillar 4: Non-Blocking MCP Configuration & Safe Fallbacks
* **File**: `src/hermes/profiles.py` & `src/registry/tools/file_ops.py`
* **Current Issue**:
  1. `profile_config()` sets `mcp_servers.aiagent.tools.include = json.dumps(sorted(tools))`. Any tool not predicted by the planner is completely hidden from Hermes.
  2. AgentHub's `read_file` tool in `src/registry/tools/file_ops.py` opens files with `open(path, 'r', encoding='utf-8')`. When asked to read a `.docx` or `.pdf` file, it throws a `UnicodeDecodeError` or unreadable byte salad.
* **Changes**:
  1. Modify `profile_config()` to allow broader tool availability, or do not restrict `tools.include` when native tool mode is enabled.
  2. Upgrade `src/registry/tools/file_ops.py:read_file`:
     Automatically check file extensions: If the file is `.docx` or `.pdf`, route to `parse_docx_file` / `parse_pdf_file` from `src/core/document_parser.py` and return structured markdown text. This acts as a bulletproof safety net if Hermes calls the MCP tool.

### Pillar 5: High-Level Task Planning
* **File**: `src/orchestrator/planner.py`
* **Current Issue**: When planning DAG tasks, AgentHub tends to break tasks into micromanaged ReAct steps (e.g. Task 1: "Read file", Task 2: "Parse content").
* **Changes**:
  When `worker_engine == "hermes"`, the planner prompt should encourage outcome-oriented tasks (e.g. "Analyze RFP document and generate proposal draft") and assign high-level goals, allowing Hermes's internal loop to manage file reading, extraction, and synthesis natively.

---

## 4. Implementation Phases & File Changes

### Phase 1: Configuration & Default Toolsets
* **[src/core/config.py](file:///d:/projects/aiagent/src/core/config.py)**:
  - Populate `hermes_default_toolsets = ["file", "terminal", "skills", "web", "code_execution"]`
  - Add `hermes_enable_native_toolsets: bool = True`
* **[src/hermes/profiles.py](file:///d:/projects/aiagent/src/hermes/profiles.py)**:
  - In `wanted_toolsets()`, ensure dynamic profiles retain default native toolsets.

### Phase 2: Skills Synchronization & Preservation
* **[src/hermes/profiles.py](file:///d:/projects/aiagent/src/hermes/profiles.py)**:
  - In `sync_exact_task_skills()`, filter deletion so only `aiagent-*` synthetic skills are removed, preserving native Hermes skills (`docx`, `pdf`, `git`, etc.).
  - Ensure `skills.external_dirs` includes both the profile's directory and global Hermes skills root.

### Phase 3: Liberating Worker Prompting & Directives
* **[src/workers/hermes_agent_worker.py](file:///d:/projects/aiagent/src/workers/hermes_agent_worker.py)**:
  - Update `_user_content()` to explain that both native tools and AgentHub MCP tools are accessible.
  - Remove `"Do NOT use skill_view"` from `_review_message()`.
  - Refine `_steering_message()` so it doesn't forbid reasoning or native skill execution.

### Phase 4: Enhancing AgentHub File Tools (Safety Net)
* **[src/registry/tools/file_ops.py](file:///d:/projects/aiagent/src/registry/tools/file_ops.py)**:
  - Update `read_file()`: Inspect file extension. For `.docx` and `.pdf`, invoke `parse_docx_file` / `parse_pdf_file` from `src.core.document_parser` and return markdown.

### Phase 5: Verification & End-to-End Testing
* **Test Case**: Proposal Generation from `.docx`
  - Create a test `.docx` file in the workspace.
  - Run an AgentHub task with `worker_engine: "hermes"`.
  - Confirm:
    1. Dynamic profile inherits native toolsets (`terminal`, `file`, `skills`).
    2. Hermes accesses the `.docx` file natively or via skill without errors.
    3. Final proposal document is generated fast and accurately.

---

## 5. Risk Assessment & Mitigations

| Risk | Mitigation |
| :--- | :--- |
| **Tool Name Collision**<br>(Hermes native `read_file` vs AgentHub `mcp__aiagent__read_file`) | Hermes prefixes MCP tools with `mcp__<server>__<tool>`. Hermes can call either native `read_file` or `mcp__aiagent__read_file`. Upgrading AgentHub's `read_file` ensures both paths succeed. |
| **Context Window Overload**<br>(Loading too many skills at once) | Hermes uses dynamic skill discovery (`skills.external_dirs` + `skill_view`) and only injects the skill content into context when actively triggered. |
| **Security / Risky Terminal Commands** | Hermes has its own built-in approval system (`respond_approval` via SSE) which AgentHub's `HermesAgentWorker` already bridges to AgentHub's clarification and approval bus. |

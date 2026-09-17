# UAOS — Universal Agent Orchestration System

**UAOS** is a dynamic, self-hosted multi-agent orchestration architecture designed to solve **any** user problem without relying on hardcoded specialized agents. 

Instead of creating separate agent implementations for every use case (e.g. SOC analysts, financial analysts, document summarizers), UAOS decomposes incoming problems into dynamic task DAGs, injects abstract skills and synthesized personas at runtime, and executes them with a **Universal Worker Agent** powered by local LLMs (Ollama, vLLM, LM Studio, llama.cpp) and durable orchestration via **Temporal**.

📖 **Deep-Dive Specifications:**
- [🏛️ **System Architecture Document (`docs/ARCHITECTURE.md`)**](file:///d:/projects/aiagent/docs/ARCHITECTURE.md) — Complete end-to-end component topology, data flows, sequence diagrams, and security matrix.
- [📐 **Algorithmic Specifications (`docs/ALGORITHMS.md`)**](file:///d:/projects/aiagent/docs/ALGORITHMS.md) — Mathematical formulations, Kahn's DAG cycle detection, guarded ReAct state machines, and greedy skill set-cover proofs.

---

## 🏛️ Architecture Overview

```
                      ┌──────────────────────┐
                      │      User Query      │
                      └──────────┬───────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │     Meta-Planner      │ ◄── [ToolRegistry Skills Catalog]
                     │  (Task Decomposition) │
                     └──────────┬────────────┘
                                │ Produces TaskDAG (Tasks + Skill Requirements)
                                ▼
                     ┌───────────────────────┐
                     │   Temporal Workflow   │ ◄── Durable state, crash recovery
                     │      (DAG Router)     │
                     └──────────┬────────────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        │ Iterates through ready tasks                  │
        ▼                                               ▼
┌──────────────────┐                         ┌──────────────────────┐
│  Skill/Tool      │                         │  Persona Synthesizer │
│  Injector        │                         │  (Dynamic System     │
│  (Maps skills    │                         │   Prompt Injection)  │
│   to ToolSpecs)  │                         └──────────┬───────────┘
└───────┬──────────┘                                    │
        │ Resolved Tools                                │ Dynamic Prompt
        └───────────────────────┬───────────────────────┘
                                │
                                ▼
                   ┌───────────────────────────┐
                   │  Universal Worker Agent   │
                   │  • Born Blank Slate       │
                   │  • Guarded ReAct Loop     │
                   │  • Destroyed After Task   │
                   │  • Zero Memory Leak       │
                   └────────────┬──────────────┘
                                │ TaskResult
                                ▼
                   ┌───────────────────────────┐
                   │     Temporal Workflow     │ ◄── Human Approval (Signals)
                   │  • DAG Progress Check     │     for High/Critical Risk
                   │  • Re-plan on Deadlock    │
                   └────────────┬──────────────┘
                                │ All Tasks Done
                                ▼
                   ┌───────────────────────────┐
                   │     Response Assembler    │
                   │   (Synthesizes Final Ans) │
                   └───────────────────────────┘
```

---

## 🔑 Key Architectural Principles

1. **No Hardcoded Domain Agents**: There is only **one** worker implementation (`UniversalWorkerAgent`). The persona (prompt) and skills (tools) are injected dynamically per-task.
2. **Abstract Skills vs Concrete Tools**: The Meta-Planner only sees high-level capability names (`web_search`, `code_execution`, `file_read`). Concrete Python functions and parameters are bound at execution time by the `ToolRegistry`.
3. **5 Guardrails for Local LLM Reliability**:
   - **Max Iterations**: Prevents infinite reasoning/tool-calling loops.
   - **Tool Name Validation**: Intercepts hallucinated tool names with feedback so the model self-corrects.
   - **Observation Size Capping**: Truncates large tool responses to prevent context window overflow.
   - **Implicit Final Answer**: Treats non-tool-call text as answer if the local model forgets protocol formatting.
   - **Timeout per Task**: Guards against hung inference servers.
4. **Durable Orchestration (Temporal)**:
   - Resilient against crashes: if worker nodes restart, Temporal replays event history from SQLite/Postgres.
   - Human-in-the-loop (HITL) approval gates use Temporal Signals, pausing without consuming CPU/GPU cycles.

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.ai) (or vLLM / LM Studio / llama.cpp) running a model (e.g. `llama3.1:8b` or `qwen2.5:7b`)
- Running [Temporal Server](https://temporal.io) (e.g. `localhost:7233`)

---

### ⚡ One-Command Start (Recommended)

Start both the **Temporal Worker** and the **FastAPI Gateway** simultaneously with a single command:

**On Windows (PowerShell):**
```powershell
.\start.ps1
```

**On Windows (CMD):**
```cmd
start.bat
```

**Cross-Platform (Python):**
```bash
python run.py
```

**On Linux/macOS:**
```bash
chmod +x start.sh && ./start.sh
```

`run.py` automatically:
1. Validates your Python version (3.11+)
2. Probes connection to your Temporal Server (`localhost:7233`)
3. Spawns both the **Temporal Worker Runner** and **FastAPI Gateway** concurrently
4. Provides graceful unified shutdown on `Ctrl+C`

---

### 🛠️ Manual / Step-by-Step Setup

If you prefer to run services in separate terminals:

```bash
# 1. Setup virtual environment & dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

# 2. Start Temporal Server (if not already running)
docker compose up -d temporal

# 3. Terminal 1: Run Temporal Worker
python -m src.orchestrator.worker_runner

# 4. Terminal 2: Run FastAPI Gateway
uvicorn src.api.main:app --port 8000 --reload
```

- **UAOS Mission Control Dashboard**: `http://localhost:8000` (or `8001`)
- **Interactive API Docs**: `http://localhost:8000/docs`
- **Temporal Web UI**: `http://localhost:8233`

---

## 🎨 Web UI & Dynamic LLM Connection

UAOS includes a modern, glassmorphic **Mission Control Dashboard** served directly at `http://localhost:8000`.

### Connecting to LM Studio on a Remote VM
You can connect to LM Studio running on a remote VM or local PC **directly from the UI**:

1. Open `http://localhost:8000/` in your browser.
2. Click the **`⚙️ LLM Connection`** button in the header bar.
3. Enter your VM's IP address and port: `http://<VM_IP>:1234/v1` (e.g. `http://192.168.1.50:1234/v1`).
4. Click **`🔄 Detect Models from VM`** — UAOS queries LM Studio's `/v1/models` and populates the available models automatically.
5. Click **`🔌 Test Connection`** to test latency and connectivity.
6. Click **`Save & Apply`** — the MetaPlanner and Universal Worker Agents immediately switch to the remote VM model at runtime without restarting!

> **Note for LM Studio on Remote VM**: In LM Studio's Local Server tab on your VM, make sure **"Serve on Local Network"** is enabled (or bound to `0.0.0.0` instead of `127.0.0.1`), and port `1234` is allowed in your VM firewall.

### Interactive Human Approval Gate (HITL)
Click **`🛡️ Approval Gate`** in the header or on the TaskDAG legend to inspect the interactive approval modal:
- **Live 15-Minute Countdown**: Ticking timer showing the time remaining before automatic escalation.
- **Human Operator Guidance Feedback**: Type guidance instructions that are injected directly into the paused agent's prompt upon approval.
- **Task Parameters Override (JSON)**: Review and modify task parameters before confirming execution.


---

## 🔌 Standardized Tool Ecosystem (MCP & OpenAPI)

UAOS eliminates custom tool wrapper code by standardizing on open protocols:

### 1. Model Context Protocol (MCP)
Connect to any community MCP server via `stdio` (subprocess) or `sse` (HTTP/SSE):
- Click **`🔌 Tool Integrations`** in the Mission Control header.
- Choose a standard preset (*GitHub, PostgreSQL, Slack, SQLite, Filesystem*) or enter a custom command/URL.
- Click **`Connect MCP Server`**: UAOS automatically queries `tools/list`, derives abstract skills for the Meta-Planner, categorizes risk levels, and wraps tools into the ReAct worker loop.
- API: `POST /api/tools/mcp/connect`, `GET /api/tools/mcp/servers`, `POST /api/tools/mcp/disconnect`.

### 2. OpenAPI 3.0 / Swagger Auto-Importer
Instantly import whole REST APIs into callable agent tools:
- Paste raw JSON/YAML or enter an OpenAPI spec URL (e.g. Petstore, Jira, internal microservice).
- Provide an optional Base URL override and Bearer token / API key.
- Click **`Import & Register Tools`**: Endpoints are parsed into typed `ToolSpec` objects with parameter validation and HTTP risk tiers (GET=LOW, POST=HIGH, DELETE=CRITICAL).
- API: `POST /api/tools/openapi/import`, `DELETE /api/tools/{tool_id}`.

---

## ⚡ Real-Time Streaming & Interactive Human-in-the-Loop

UAOS provides an enterprise-grade real-time streaming pipeline and interactive approval workflow:

### 1. Server-Sent Events (SSE) Streaming
- **`LocalLLMClient.chat_stream`**: Streams token deltas chunk-by-chunk from local LLM inference engines (Ollama, vLLM, LM Studio) with zero buffering delay.
- **`EventBus` Pub/Sub**: In-memory event broadcaster featuring a circular ring buffer ($C=500$) for history replay, ensuring newly connected or refreshed browser clients immediately receive past tokens and state transitions.
- **Universal Worker Callbacks**: Emits character-by-character reasoning tokens (`token`), tool execution start badges (`tool_start`), and completion notifications (`tool_end`) during the ReAct loop.
- **Endpoint**: `GET /stream/{workflow_id}` streams events directly to the Mission Control dashboard.

### 2. Interactive Human Approval Gate (HITL)
- **Operator Guidance Feedback**: Reviewers can inject guidance comments (e.g., *"Approved, but make sure to exclude 2023 archived data and verify backup checksum"*) directly into the agent's prompt before execution resumes.
- **Parameter Override Editor**: Interactive collapsible JSON editor in the approval modal enabling reviewers to tune or restrict task parameters at runtime before approval.
- **15-Minute Countdown Timer & Auto-Escalation**: Approval gates pause durably via Temporal (`workflow.wait_condition`) racing against an escalation timeout (default 15 minutes / 900s). If the approval gate times out, an automatic escalation policy executes (`escalate_approval` activity), broadcasting critical alerts to administrators.

---

## 📡 API Reference

### `POST /solve`
Submit a problem and wait synchronously for the full result.
```bash
curl -X POST http://localhost:8000/solve \
  -H "Content-Type: application/json" \
  -d '{"query": "Analyze recent cybersecurity vulnerabilities in OpenSSL and suggest mitigations"}'
```

### `POST /solve/async`
Submit a problem asynchronously and get a workflow ID immediately.
```bash
curl -X POST http://localhost:8000/solve/async \
  -H "Content-Type: application/json" \
  -d '{"query": "Calculate the factorial of 25 and write results to file"}'
```

### `GET /stream/{workflow_id}`
Connect to real-time Server-Sent Events (SSE) stream for live tokens, tool lifecycle events, and approval requests.
```bash
curl -N http://localhost:8000/stream/uaos-wf-123
```

### `GET /status/{workflow_id}`
Check execution progress, query pending task details, or verify if a workflow is awaiting human approval.

### `POST /approve/{workflow_id}`
Approve or reject a paused task with optional operator guidance and runtime parameter overrides.
```bash
curl -X POST http://localhost:8000/approve/uaos-wf-123 \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "guidance": "Approved, but execute in sandbox container first.",
    "modified_params": {"dry_run": true, "max_results": 10}
  }'
```

### `GET /tools`
List all registered tools, their parameters, source types (`native`, `mcp`, `openapi`), and the abstract skills they satisfy.

---

## 🛠️ Adding New Tools

Adding a capability requires **zero changes** to orchestration or planning code. Simply define an async function and expose a `ToolSpec` ending with `_SPEC` in `src/registry/tools/`:

```python
# src/registry/tools/calculator.py
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

async def evaluate_math(expression: str) -> str:
    """Evaluates a math expression."""
    return str(eval(expression))

CALCULATOR_SPEC = ToolSpec(
    tool_id="math_calculator",
    name="calculator",
    description="Evaluates mathematical expressions safely",
    skills_provided=["math", "calculation"],
    parameters={
        "expression": {
            "type": "string",
            "description": "Math expression to evaluate, e.g. 2 * (3 + 4)",
            "required": True,
        }
    },
    risk_level=RiskLevel.LOW,
    function=evaluate_math,
)
```

Auto-discovery will pick it up on next boot. The Meta-Planner will immediately know that `math` and `calculation` skills exist!

---

## 🧪 Running Tests

```bash
# Run all unit and integration tests
pytest -v
```

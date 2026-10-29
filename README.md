# UAOS & Fleet Studio — Sovereign Multi-Agent Orchestration & Governance

**UAOS (Universal Agent Orchestration System)** and **Fleet Studio** form an enterprise-grade, self-hosted multi-agent orchestration, governance, and control plane designed to solve complex multi-modal problems without relying on hardcoded, brittle agent silos.

Instead of handcrafting specialized conversational agents (e.g., dedicated SOC analysts, document summarizers, or pricing estimators) that easily drift off-task, UAOS decomposes user missions into **dynamic task DAGs**, synthesizes dedicated **Autonomous Execution Units (AEUs)** per task node, enforces strict **sovereign air-gap governance**, and executes them across **Dual Worker Engines** (`UniversalWorkerAgent` & `HermesAgentWorker`) backed by durable **Temporal** orchestration or a lightweight **Standalone Direct Engine**.

---

📖 **Authoritative Deep-Dive Specifications:**
- 🏛️ [**System Architecture Document (`docs/ARCHITECTURE.md`)**](file:///d:/projects/aiagent/docs/ARCHITECTURE.md) — Complete component topologies, communication protocols, dual-worker lifecycle, sequence diagrams, and security matrix.
- 📐 [**Algorithmic Specifications (`docs/ALGORITHMS.md`)**](file:///d:/projects/aiagent/docs/ALGORITHMS.md) — Mathematical formalisms, Kahn's DAG cycle validation, 5-guardrail ReAct FSM, greedy skill resolution, BM25 memory retrieval, AST-guarded skill distillation, and Arena ELO ranking.
- 🎯 [**Enterprise RFP Demo Guide (`docs/FLEET_STUDIO_PROPOSAL_DEMO_GUIDE.md`)**](file:///d:/projects/aiagent/docs/FLEET_STUDIO_PROPOSAL_DEMO_GUIDE.md) — Step-by-step walkthrough converting raw RFP documents into submission-ready proposals and pricing models.
- 🚀 [**Interactive Demo Script (`docs/DEMO_GUIDE.md`)**](file:///d:/projects/aiagent/docs/DEMO_GUIDE.md) — Fast-track verification script for live audience demonstrations.

---

## 🏛️ System Architecture Topology

```
                      ┌─────────────────────────────────────────┐
                      │    User Query & Multi-Modal Inputs      │
                      │   (Word .docx, PDF, Excel, JSON, REST)  │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │              Meta-Planner               │ ◄── [ToolRegistry Skills Index]
                      │     (TaskDAG Dynamic Decomposition)     │ ◄── [FTS5 Long-Term Memory]
                      └────────────────────┬────────────────────┘
                                           │ Produces TaskDAG (Nodes, Dependencies & Risk Tiers)
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │         MissionFleetArchitect           │ ◄── Anti-Persona Mandate:
                      │    (Synthesizes Dedicated AEUs per Node)│     1 Task Node = 1 Micro-Agent
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │       Durable Temporal Workflow         │ ◄── SQLite/Postgres Event Replay
                      │   (DAG Router / Standalone Direct Fall) │ ◄── Non-blocking signal pause
                      └────────────────────┬────────────────────┘
                                           │
         ┌─────────────────────────────────┴─────────────────────────────────┐
         │ High / Critical Risk Detected                                     │ Standard Low-Risk Path
         ▼                                                                   ▼
┌─────────────────────────────────┐                         ┌─────────────────────────────────┐
│     Decision Rooms (HITL)       │                         │         Worker Factory          │
│ • Live 15-Min Countdown Timer   │                         │  • Resolves Engine per Profile  │
│ • Human Guidance Comment Input  │                         │  • Universal vs Hermes Native   │
│ • JSON Parameter Overrides      │                         └────────────────┬────────────────┘
│ • Auto-Escalation Webhook Alert │                                          │
└────────────────┬────────────────┘                                          │
                 │ Approved with Operator Guidance                           │
                 └─────────────────────────┬─────────────────────────────────┘
                                           │
         ┌─────────────────────────────────┴─────────────────────────────────┐
         ▼                                                                   ▼
┌─────────────────────────────────┐                         ┌─────────────────────────────────┐
│     Universal Worker Agent      │                         │       Hermes Agent Worker       │
│ • Born Blank-Slate per Task     │                         │ • Hermes v0.21.x Native Engine  │
│ • 5-Guardrail ReAct FSM         │                         │ • Dynamic Profile Provisioning  │
│ • Tool Hallucination Intercept  │                         │ • Local Loopback JSON-RPC Bridge│
│ • Zero Cross-Task Memory Leak   │                         │ • Native Hermes Skills Catalog  │
└────────────────┬────────────────┘                         └────────────────┬────────────────┘
                 │                                                           │
                 └─────────────────────────┬─────────────────────────────────┘
                                           │ Scoped Tool Invocations
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │    Standardized Protocol & Tool Fabric  │
                      │ • Model Context Protocol (stdio / SSE)  │
                      │ • OpenAPI 3.0 / Swagger Auto-Importer   │
                      │ • 13 Enterprise Security Connectors     │
                      │ • Native Subprocess Code / File Tools   │
                      └────────────────────┬────────────────────┘
                                           │ Execution Traces & Outputs
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │           Response Assembler            │
                      │  • Synthesizes Deliverable Artifacts    │
                      │  • AST Skill Distiller (Extracts Tools) │
                      │  • SQLite FTS5 Memory Update (Episodes) │
                      └────────────────────┬────────────────────┘
                                           │ Real-Time SSE Streams
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │        Fleet Studio Control Plane       │
                      │    (Next.js 16 / React 19 / xyflow DAG) │
                      └─────────────────────────────────────────┘
```

---

## 🔑 Key Architectural Breakthroughs

1. **Anti-Persona Mandate (1 Task Node = 1 Dedicated Micro-Agent)**:
   - There are no static, monolithic agent roles.
   - For every task node in the decomposed DAG, the `MissionFleetArchitect` synthesizes a dedicated **Autonomous Execution Unit (AEU)** with bespoke instructions, scoped tools, and synthetic resilience directives.
2. **Dual Worker Execution Engines**:
   - **`UniversalWorkerAgent`**: A pure blank-slate ReAct worker with zero memory leaks between tasks, defended by **5 Local LLM Reliability Guardrails**:
     - *Iteration Ceiling*: Halts runaway loops at $K_{\max} = 10$.
     - *Tool Hallucination Intercept*: Provides real-time feedback with registered tool names when models hallucinate commands.
     - *Observation Capping*: Truncates responses at 4,000 characters to safeguard the context window.
     - *Implicit Final Answer*: Captures valid output when small models omit syntax tags.
     - *Execution Timeout*: Async cancellation preventing frozen inference sockets.
   - **`HermesAgentWorker`**: Native integration with Hermes Agent v0.21.x, supporting persistent profiles, dynamic provisioning, skills catalog, loopback bridge, and an embedded MCP Server.
3. **Sovereign Decision Rooms & Human-in-the-Loop (HITL)**:
   - High-risk and critical actions cleanly suspend execution via Temporal Signals.
   - Operators can review pending operations in the interactive modal, provide **guidance feedback**, and override task parameters in real time.
   - Includes a live **15-minute countdown timer** racing against an automatic escalation policy.
4. **Standardized Tool Ecosystem**:
   - **Model Context Protocol (MCP)**: Native stdio and SSE client + embedded Hermes MCP Server.
   - **OpenAPI 3.0 / Swagger Auto-Importer**: Ingests external REST APIs instantly with HTTP risk tiering (GET=LOW, POST=HIGH, DELETE=CRITICAL).
   - **13 Enterprise Security Connectors**: Direct integration with CrowdStrike Falcon, Microsoft Defender, Microsoft Entra ID, Sentinel, Splunk, Elasticsearch, Fortigate, Okta, Palo Alto Networks, SentinelOne, TheHive, VirusTotal, and AbuseIPDB.
5. **Long-Term Memory & Skill Distillation**:
   - **Memory Store**: SQLite database with FTS5 virtual tables indexing past execution episodes, verified system facts, and operational lessons with automatic secret masking.
   - **Skill Distiller**: Analyzes successful multi-step workflow traces, synthesizes reusable Python tools, verifies safety via static **AST inspection** (blocking forbidden imports and calls), and promotes them into the active `ToolRegistry`.
6. **File-Backed Workflow Artifact Scratchpad & Factual Accuracy Hardening**:
   - **Lossless Artifact Scratchpad**: `WorkflowArtifactExchange` writes complete intermediate task payloads and source documents to `data/artifacts/{workflow_id}/`, eliminating context truncation cliffs.
   - **Structured JSON Auto-Extraction**: Automatically parses embedded JSON blocks from task results into structured artifacts (`*_payload.json`).
   - **Semantic DAG Dependency Repair**: `_repair_dag_dependencies` automatically links downstream pricing and synthesis tasks to predecessor extraction tasks, enforcing structured output contracts.
   - **Mandatory Tool Directives**: Strict ground-truth directives require specialist agents to execute tools to gather real evidence before formulating conclusions, preventing memory hallucinations.
   - **Supervisor Factual Verification**: Evaluates 800-character excerpts with disk artifact pointers and intercepts unpopulated placeholder tokens (`[insert ...]`, `TBD`, `TODO`).

---

## 🌐 Network Topology & Active Endpoints

| Service / Component | Default Port / URL | Description | Status Check |
| :--- | :--- | :--- | :--- |
| **Fleet Studio Web UI** | `http://localhost:3000/` | Next.js 16 / React 19 / Turbopack / xyflow Mission Control | Rendered in browser |
| **AgentHub API Gateway** | `http://localhost:8001/` *(or `8000`)* | FastAPI backend for execution, streaming, uploads, and auth | `GET /auth/me` or `/health` |
| **Interactive API Docs** | `http://localhost:8001/docs` | Swagger / OpenAPI interactive documentation | Interactive in browser |
| **Temporal Web UI** | `http://localhost:8234/` *(or `8233`)* | Temporal durable workflow execution dashboard | Browser dashboard |
| **Temporal Server gRPC** | `localhost:7234` *(or `7233`)* | gRPC durable state log | Auto-probed by launcher |
| **Local Sovereign LLM** | `http://<IP>:1234/v1` | LM Studio, Ollama, or vLLM OpenAI-compatible server | `GET /v1/models` |

---

## 🚀 Quickstart

### Prerequisites
- **Python 3.11+**
- **Node.js 18+ & npm** (for Fleet Studio UI)
- **Docker Desktop** (optional, for Temporal container stack — standalone fallback is built-in)
- Local LLM server (e.g., [LM Studio](https://lmstudio.ai), [Ollama](https://ollama.ai), or vLLM)

---

### ⚡ One-Command Start (Recommended)

Start the entire autonomous backend (Temporal Worker + FastAPI Gateway + Auto Port Detection) with a single command:

**On Windows (Command Prompt):**
```cmd
start.bat
```

**On Windows (PowerShell):**
```powershell
.\start.ps1
```

**Cross-Platform (Python):**
```bash
python run.py
```

`run.py` automatically:
1. Validates Python 3.11+ and configures the Windows Proactor event loop.
2. Checks Temporal connectivity (ports `7234/7233`) and auto-starts Docker containers if available.
3. Automatically scans and binds available gateway ports (`8001` or `8000`).
4. Spawns the **Temporal Worker Runner** and **FastAPI Gateway** with unified Ctrl+C shutdown.

---

### 🎨 Starting the Fleet Studio Web Control Plane

In a separate terminal:

```bash
cd frontend/frontend
npm install
npm run dev
```

Open **`http://localhost:3000`** in your browser to access Fleet Studio Mission Control!

---

## 🛠️ Step-by-Step Manual Setup

If you prefer to run services individually:

```bash
# 1. Setup Python virtual environment & dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

# 2. Start Temporal container stack (if using Docker)
docker compose up -d postgresql temporal temporal-ui

# 3. Terminal 1: Run Temporal Worker
python -m src.orchestrator.worker_runner

# 4. Terminal 2: Run FastAPI Gateway
uvicorn src.api.main:app --port 8001 --reload

# 5. Terminal 3: Run Fleet Studio Frontend
cd frontend/frontend
npm run dev
```

---

## ⚙️ Dynamic LLM Configuration & VM Connection

You can connect to any local or remote OpenAI-compatible inference server (LM Studio, Ollama, vLLM) **directly from the UI without restarting services**:

1. Open `http://localhost:3000/` (or the backend at `http://localhost:8001/`).
2. Click **`⚙️ LLM Connection`** in the header.
3. Enter your server's endpoint: `http://<IP>:1234/v1` (e.g., `http://192.168.1.50:1234/v1`).
4. Click **`🔄 Detect Models`** — queries `/v1/models` and populates the available model IDs automatically.
5. Click **`🔌 Test Connection`** to measure latency and verify token throughput.
6. Click **`Save & Apply`** — both the Meta-Planner and Worker Agents switch to the new model immediately at runtime.

---

## 🛡️ Sovereign Decision Rooms & HITL Approval Gates

When tasks perform sensitive or irreversible actions (such as mutating production databases, deleting files, or executing system commands):
1. **Air-Gap Verification**: Pre-flight scanners inspect data residency constraints before execution.
2. **Interactive Approval Modal**:
   - **15-Minute Countdown Timer**: Displays remaining time before auto-escalation.
   - **Operator Guidance Input**: Reviewers can inject instructions (e.g., *"Approved, but filter results to 2024 and verify backup checksum first"*) that are injected directly into the worker prompt.
   - **Parameter Overrides**: Operators can edit the JSON payload before confirming.
   - **Automatic Escalation**: If the countdown expires without human response, the workflow triggers the `escalate_approval` activity, alerting administrators via webhooks.

---

## 📡 Core API Reference

### `POST /solve`
Submit a problem and wait synchronously for the full result.
```bash
curl -X POST http://localhost:8001/solve \
  -H "Content-Type: application/json" \
  -d '{"query": "Analyze cybersecurity vulnerabilities in OpenSSL and generate mitigations"}'
```

### `POST /solve/async`
Submit a problem asynchronously and receive a workflow tracking ID immediately.
```bash
curl -X POST http://localhost:8001/solve/async \
  -H "Content-Type: application/json" \
  -d '{"query": "Parse uploaded government RFP and generate tiered labor pricing"}'
```

### `GET /stream/{workflow_id}`
Connect to real-time Server-Sent Events (SSE) streaming live reasoning tokens, tool start/end badges, and approval alerts.
```bash
curl -N http://localhost:8001/stream/uaos-wf-123
```

### `POST /approve/{workflow_id}`
Approve or reject a paused task with optional guidance and parameter overrides.
```bash
curl -X POST http://localhost:8001/approve/uaos-wf-123 \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "guidance": "Approved, execute within sandbox container first.",
    "modified_params": {"dry_run": true, "max_results": 10}
  }'
```

### `GET /tools`
List all registered tools, their parameter schemas, risk tiers, and abstract skills satisfied.

---

## 🧪 Running Verification Tests

```bash
# Run all unit and integration tests
pytest -v

# Run dedicated Hermes worker integration tests
run_hermes_tests.bat

# Run complete system verification suite
verify.bat
```

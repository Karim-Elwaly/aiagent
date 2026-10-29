# UAOS & Fleet Studio — System Architecture Reference

**Document Version:** 2.0.0  
**Status:** Production & Enterprise Ready  

The complete, authoritative Architecture Document has been published to:  
👉 [**`docs/ARCHITECTURE.md`**](file:///d:/projects/aiagent/docs/ARCHITECTURE.md)

---

### Executive Table of Contents

1. **Architectural Philosophy & Core Tenets**
   - Dynamic TaskDAG Planning vs Brittle Conversational Multi-Agent Loops
   - Dual Worker Execution Engines (`UniversalWorkerAgent` & `HermesAgentWorker`)
   - Anti-Persona Mandate: 1 Task Node = 1 Dedicated Autonomous Execution Unit (AEU)
   - Durable Temporal Orchestration with Standalone Direct Fallback
   - Sovereign Governance & Decision Rooms (HITL, 15-Minute Countdown, Escalation Webhooks)
   - Standardized Protocol Fabric (MCP stdio/SSE, OpenAPI 3.0, 13 Enterprise Security Connectors)

2. **Global System Topology**
   - End-to-End Mermaid Component Flow
   - Presentation Layer: Fleet Studio Next.js 16 Mission Control (`http://localhost:3000`)
   - Gateway Layer: AgentHub FastAPI Gateway (`http://localhost:8001`) & Real-Time Event Bus ($C=500$)
   - Orchestration Layer: Temporal Server (`7234/7233`) & Direct Execution Engine
   - Memory & Distillation: SQLite FTS5 Long-Term Store & AST-Guarded Skill Distiller
   - Local Sovereign Inference: LM Studio, Ollama, vLLM

3. **Component Deep Dive**
   - Meta-Planner & Pre-Flight Environment Scanner (`src/brain/`)
   - Durable DAG Router & Standalone Direct Engine (`src/orchestrator/`)
   - Dual Execution Engines & Worker Factory (`src/workers/`)
   - Dynamic Hermes Profile Management & Loopback Bridge (`src/hermes/`)
   - Specialized Fleet Composer & Multi-Agent Arena (`src/fleet/`)
   - Tool Ecosystem & 13 Enterprise Security Connectors (`src/registry/`, `src/connectors/`)
   - Governance, Decision Rooms & Sovereign Compliance (`src/governance/`, `src/core/`)
   - Long-Term Memory Store & Semantic Retriever (`src/memory/`)
   - Autonomous Skill Distillation Engine (`src/skills/`)
   - Fleet Studio Next.js 16 Web Application (`frontend/frontend/`)

4. **Human-in-the-Loop & Decision Room Sequence Flow**
   - Cryptographic Temporal Signals & Interactive Approval Modal
   - Operator Guidance Feedback & Runtime Parameter Overrides
   - 15-Minute Timeout Racing Against Escalation Webhooks

5. **Security, Isolation & Air-Gap Compliance Matrix**
   - Sandboxed Execution, AST Code Verification, Credential Masking & Data Residency

6. **Directory Structure & Complete Module Organization**

# UAOS System Architecture Reference

The complete, authoritative Architecture Document has been published to:
👉 [**`docs/ARCHITECTURE.md`**](docs/ARCHITECTURE.md)

### Summary Table of Contents
1. **Architectural Philosophy & Core Tenets**
   - Dynamic TaskDAG Decomposition vs Hardcoded Multi-Agent Conversations
   - Blank-Slate Universal Workers
   - Durable Temporal Orchestration
   - Standardized Tool Ecosystem (MCP & OpenAPI)
2. **Global System Topology**
   - Mermaid End-to-End Component Flow
   - Protocol Boundaries (REST, SSE, JSON-RPC, Temporal gRPC)
3. **Component Deep Dive**
   - Meta-Planner (`src/brain/meta_planner.py`)
   - Durable DAG Router (`src/orchestrator/workflow.py`)
   - Tool Registry & Adapters (`src/registry/`)
   - Persona Synthesizer (`src/persona/synthesizer.py`)
   - Universal Worker Agent (`src/workers/universal_worker.py`)
   - Real-Time Event Bus (`src/orchestrator/event_bus.py`)
4. **Human-in-the-Loop (HITL) & Escalation Sequence Diagram**
5. **Security & Isolation Matrix**
6. **Project Directory & Module Organization**

---
name: subagent_delegation
description: Decompose massive multi-phase objectives and spawn isolated Universal Worker subagents with dedicated scopes and independent ReAct loops.
author: Nous Research / Hermes Orchestration
version: 1.5.0
license: MIT
metadata:
  category: orchestration
  skills: [subagent_delegation, multi_agent_orchestration, task_decomposition, parallel_execution]
  risk_level: medium
parameters:
  subtask_goal:
    type: string
    description: Precise scoped goal for the subagent to accomplish
    required: true
  assigned_skills:
    type: array
    description: List of tools/skills granted to the subagent
    required: false
  timeout_seconds:
    type: integer
    description: Max execution duration before returning intermediate synthesis
    default: 120
---

# Subagent Delegation Skill 👥

Spawns independent worker processes to collapse complex multi-turn problems.
Mechanisms:
- Creates fresh execution contexts preventing token degradation and distraction.
- Runs specialized subtasks (e.g. data scraping, deep code review, math proofs) in parallel.
- Aggregates subagent outputs into a coherent synthesized solution for the parent workflow.

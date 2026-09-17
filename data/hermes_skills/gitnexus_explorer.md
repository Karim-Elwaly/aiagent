---
name: gitnexus_explorer
description: Deep codebase architecture reconstruction, call graph topology extraction, and cross-module dependency tracing.
author: Nous Research / Hermes Research
version: 1.1.0
license: MIT
metadata:
  category: research
  skills: [gitnexus_explorer, code_analysis, architecture_recovery, dependency_graph, AST]
  risk_level: low
parameters:
  repo_path:
    type: string
    description: Path to repository or submodule to explore
    required: true
  focus_module:
    type: string
    description: Primary module or entry point to trace from
    required: false
  generate_graph:
    type: boolean
    description: Output structured Mermaid or DOT dependency diagram
    default: true
---

# GitNexus Explorer Skill 🔍

Reconstructs architectural topology from code repositories.
Capabilities:
- Scans symbol definitions, class hierarchies, and async call pipelines.
- Identifies critical hotpaths, cyclical import deadlocks, and orphaned utility modules.
- Generates modular architectural summaries and Mermaid component diagrams.

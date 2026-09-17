---
name: claude_code
description: Deep pair programming with automated test-driven iteration, file navigation, and rigorous code verification.
version: 1.0.0
author: nous_research
category: autonomous-ai-agents
risk_level: medium
metadata:
  skills: [claude_code, pair_programming, test_driven_dev, codebase_search]
---

# Claude-Code Style Autonomous Coding Skill

Emulates high-precision autonomous software engineering with full test-driven loops and zero hallucinated diffs.

## Workflow Rules

1. **Locate Before Editing**:
   - Use `file_read` or `session_search` to inspect existing code patterns before modifying.
   - Never assume an API or signature exists without verifying import statements.

2. **Test-First Validation**:
   - Locate existing test suites or write reproducible regression tests first.
   - Run tests with `execute_code` to confirm failure prior to fix.

3. **Surgical Patching**:
   - Apply edits with `patch_file` rather than rewriting whole files.
   - Verify all tests pass cleanly after patch application.

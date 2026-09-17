---
name: computer_use
description: Autonomous desktop and browser coordinate automation, screenshot vision grounding, and keystroke dispatch.
version: 1.0.0
author: nous_research
category: autonomous-ai-agents
risk_level: medium
metadata:
  skills: [computer_use, gui_automation, screenshot_grounding, desktop_control]
---

# Computer Use & Desktop Control Skill

Enables the agent to inspect screen state via screenshots, ground UI elements to pixel coordinates, and perform mouse/keyboard actions.

## Operational Workflow

1. **Visual Perception**:
   - Capture current screen or viewport state via `vision_analyze`.
   - Identify UI elements, buttons, input fields, and dialogs.

2. **Coordinate Grounding**:
   - Estimate bounding box coordinates `[x, y]` relative to viewport resolution.
   - Confirm element visibility before issuing click or typing commands.

3. **Safe Execution**:
   - For destructive actions (e.g. closing unsaved work, sending emails, deleting data), request operator confirmation with `clarify_question`.
   - Implement post-action verification: capture another screenshot to confirm state change.

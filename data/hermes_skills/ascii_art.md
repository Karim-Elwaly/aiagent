---
name: ascii_art
description: Render stylish terminal ASCII banners, ANSI color diagrams, retro typography, and CLI status dashboards.
version: 1.0.0
author: nous_research
category: creative
risk_level: low
metadata:
  skills: [ascii_art, terminal_graphics, ansi_banners, cli_typography]
---

# ASCII Art & Terminal Graphics Skill

Enables the agent to present retro typography, system banners, and ASCII architecture flowcharts in terminal logs and CLI interfaces.

## Guidelines

1. **Box Drawing**:
   - Use Unicode box-drawing characters (`┌─┐│└─┘`, `╔═╗║╚═╝`) for sharp borders.
   - Keep width constrained to <= 80 columns to prevent line-wrapping on narrow TUIs.

2. **Banners & Badges**:
   - Create recognizable headers for major milestones (e.g. `UAOS`, `HERMES`, `SUCCESS`).
   - Use ANSI color escape codes when printing to raw terminals.

3. **Status Graphs**:
   - Format dependency graphs and execution pipelines using clean directional arrows (`───▶`, `▲`, `▼`).

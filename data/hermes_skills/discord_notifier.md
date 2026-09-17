---
name: discord_notifier
description: Format rich Discord webhook embeds, broadcast agent status updates, error alerts, and workflow execution summaries.
version: 1.0.0
author: nous_research
category: communication
risk_level: low
metadata:
  skills: [discord_notifier, webhook_alerts, chat_notifications, embed_builder]
---

# Discord Webhook & Agent Notification Skill

Dispatches structured messages, rich card embeds, and color-coded status badges to Discord channels.

## Message Format Standards

1. **Color Codes**:
   - Success (`#10b981` Emerald Green): Completed workflows, verified builds.
   - Warning (`#f59e0b` Amber): Non-fatal retries, rate limits, threshold warnings.
   - Error (`#ef4444` Crimson): Workflow aborts, security anomalies, fatal exceptions.

2. **Embed Structure**:
   - `title`: Short descriptive headline with emoji icon.
   - `description`: Executive 2-3 sentence overview.
   - `fields`: Key-value pairs for `Workflow ID`, `Duration`, `Tokens Used`, `Status`.
   - `footer`: "UAOS Hermes Agent • Timestamp".

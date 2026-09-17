---
name: apple_reminders
description: Parse natural language tasks into scheduled reminders with deadlines, priority tags, and recurring alarm triggers.
version: 1.0.0
author: nous_research
category: productivity
risk_level: low
metadata:
  skills: [apple_reminders, task_scheduling, deadline_tracking, reminder_alerts]
---

# Apple Reminders & Task Dispatch Skill

Converts conversational deadlines and follow-ups into structured calendar items and reminder alerts.

## Operation

1. **Natural Language Parsing**:
   - Detect relative times ("tomorrow at 9am", "every Monday at 10", "in 3 hours").
   - Convert to ISO 8601 UTC timestamps with operator timezone offset.

2. **Priority Classification**:
   - `High`: Critical bugs, immediate client deadlines, server downtime.
   - `Medium`: Feature milestones, scheduled reviews.
   - `Low`: Exploratory reading, backlogged ideas.

3. **Automation Bridge**:
   - For recurring background checks, register a cron entry via `cronjob_manage`.

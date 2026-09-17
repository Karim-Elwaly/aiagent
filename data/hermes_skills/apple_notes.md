---
name: apple_notes
description: Create, search, update, and format rich notes, markdown journals, and knowledge bases with Apple Notes & local folders.
version: 1.0.0
author: nous_research
category: productivity
risk_level: low
metadata:
  skills: [apple_notes, note_taking, knowledge_base, markdown_notes]
---

# Apple Notes & Knowledge Base Synchronization Skill

Enables the agent to organize thoughts, draft meeting minutes, and store knowledge artifacts in organized folders.

## Guidelines

1. **Note Structuring**:
   - Use clean H1 headers for note titles with ISO date metadata.
   - Use checklists (`- [ ]`) for action items.
   - Keep code snippets inside tagged syntax blocks.

2. **Categorization**:
   - Automatically assign notes to folders (e.g. `Projects`, `Meetings`, `Research`, `Quick Notes`).
   - Append relevant tags (`#ai`, `#architecture`, `#todo`) at the bottom of the note.

3. **Memory Integration**:
   - For long-lived project facts, store a summary in `memory_manager` alongside the note.

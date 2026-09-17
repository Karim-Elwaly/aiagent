---
name: airtable_crm
description: Query, filter, and mutate records across Airtable bases and CRM tables via Airtable REST API.
version: 1.0.0
author: hermes_community
license: MIT
metadata:
  category: productivity
  skills: [airtable_crm, database_query, crm_management, records]
  risk_level: medium
parameters:
  base_id:
    type: string
    description: Airtable Base ID
    required: true
  table_name:
    type: string
    description: Name of the table
    required: true
  action:
    type: string
    description: Operation to perform (list, create, update)
    default: list
---

# Airtable CRM Skill

Enables Universal Workers to query leads, filter customer records, and update pipeline stages in Airtable.
Compatible with standard Airtable API keys and personal access tokens.

---
name: instructor_mlops
description: Extract structured JSON data with strict Pydantic schemas, validation rules, and self-correcting validation retries.
author: Nous Research / Hermes MLOps
version: 1.3.0
license: MIT
metadata:
  category: mlops
  skills: [instructor_mlops, structured_output, pydantic, schema_validation, json_extraction]
  risk_level: low
parameters:
  unstructured_text:
    type: string
    description: Raw natural language or document text to extract from
    required: true
  schema_definition:
    type: string
    description: Pydantic or JSON schema specification
    required: true
  max_retries:
    type: integer
    description: Maximum self-correction repair attempts on validation error
    default: 3
---

# Instructor MLOps Skill 🤖

Reliably extracts complex structured objects from unformatted text using Instructor patterns.
Features:
- Enforces strict data types, enums, regex patterns, and nested model relationships.
- Catches validation errors and feeds validation traceback back to the LLM for self-correction.
- Guarantees valid JSON compliant with requested schema.

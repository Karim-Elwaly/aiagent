---
name: architecture_diagram
description: Generates dark-themed SVG architecture and cloud infrastructure diagrams from text descriptions.
version: 1.0.0
author: hermes_community
license: MIT
metadata:
  category: creative
  skills: [architecture_diagram, diagram, svg, cloud_architecture]
  risk_level: low
parameters:
  system_description:
    type: string
    description: Detailed description of the system components and data flow
    required: true
  diagram_type:
    type: string
    description: Type of diagram (e.g. cloud_architecture, sequence, component)
    required: false
---

# Architecture Diagram Skill

Generates clean, dark-themed SVG architecture and infrastructure diagrams.
Accepts a system description and outputs structured SVG layout code.

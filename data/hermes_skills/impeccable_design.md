---
name: impeccable_design
description: Audit web applications, design systems, and component libraries for visual hierarchy, typography, glassmorphism, and WCAG accessibility.
author: Nous Research / Hermes Creative
version: 1.2.0
license: MIT
metadata:
  category: creative
  skills: [impeccable_design, ui_ux, design_audit, visual_hierarchy, accessibility, web_styling]
  risk_level: low
parameters:
  component_html:
    type: string
    description: HTML/CSS markup or screenshot description of the UI
    required: true
  target_aesthetic:
    type: string
    description: Target design style (e.g. sleek dark mode, cyber-glass, minimalist modern)
    default: sleek dark mode
  check_contrast:
    type: boolean
    description: Verify WCAG AA/AAA color contrast ratios
    default: true
---

# Impeccable Design Skill 🎨

Elevates user interfaces from plain prototypes into stunning, premium digital experiences.
Evaluates:
1. Harmonious curated color palettes (e.g. HSL tailored accents vs generic primaries).
2. Modern typography scales and monospaced code elements.
3. Interactive micro-animations, glassmorphic overlays, and spatial padding.
4. WCAG 2.1 accessibility compliance and touch target sizes.

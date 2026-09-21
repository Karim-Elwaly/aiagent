---
name: here_now
description: "Real-time contextual briefing: compute local sunrise/sunset, current timezone offsets, weather forecasts, and regional news briefs."
author: Nous Research / Hermes Productivity
version: 1.1.0
license: MIT
metadata:
  category: productivity
  skills: [here_now, environmental_briefing, weather, timezone, local_intelligence]
  risk_level: low
parameters:
  location:
    type: string
    description: City, country, or coordinates to brief on
    required: true
  include_weather:
    type: boolean
    description: Fetch current meteorological conditions and forecast
    default: true
---

# Here Now Skill 🌐

Provides real-time local intelligence and operational context.
Features:
- UTC and local timezone conversion with daylight savings handling.
- Weather conditions (temperature, humidity, wind, barometric pressure).
- Local operational context for scheduled task execution windows.

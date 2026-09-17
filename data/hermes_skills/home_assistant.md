---
name: home_assistant
description: Inspect IoT entity states, trigger scenes, adjust climate/lights, and automate smart home devices via Home Assistant REST API.
version: 1.0.0
author: nous_research
category: integrations
risk_level: medium
metadata:
  skills: [home_assistant, iot_automation, smart_home, rest_api]
---

# Home Assistant IoT Automation Skill

Enables the agent to interact with smart home sensors, lighting, switches, climate controllers, and scenes.

## API Patterns

1. **Entity State Query**:
   Fetch current state of entities (`light.*`, `switch.*`, `sensor.*`, `climate.*`):
   ```http
   GET /api/states/sensor.temperature_living_room
   ```

2. **Service Call Execution**:
   Turn on devices or set values via domain services:
   ```http
   POST /api/services/light/turn_on
   {"entity_id": "light.office", "brightness": 255, "color_temp": 300}
   ```

3. **Safety & Confirmation**:
   - For security-sensitive actions (locks, garage doors, alarm systems), prompt operator with `clarify_question` before dispatching API mutations.

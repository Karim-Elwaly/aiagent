---
name: fitness_nutrition
description: Quantitative nutritional science: calculate basal metabolic rate (BMR), total daily energy expenditure (TDEE), and macronutrient partitioning.
author: Nous Research / Hermes Health
version: 1.0.0
license: MIT
metadata:
  category: health
  skills: [fitness_nutrition, metabolic_calculation, macronutrient_planning, health_science]
  risk_level: low
parameters:
  body_weight_kg:
    type: number
    description: Current weight in kilograms
    required: true
  height_cm:
    type: number
    description: Height in centimeters
    required: true
  activity_level:
    type: string
    description: Sedentary, lightly_active, moderately_active, very_active
    default: moderately_active
  fitness_goal:
    type: string
    description: Maintenance, fat_loss, muscle_hypertrophy
    default: maintenance
---

# Fitness & Nutrition Skill 🥗

Performs precision metabolic calculations using Mifflin-St Jeor and Katch-McArdle models.
Computes:
- BMR and Activity-adjusted TDEE.
- Gram targets for Protein, Carbohydrates, and Fats tailored to training objectives.
- Caloric surplus or deficit recommendations with safety thresholds.

---
name: drug_discovery
description: "Computational cheminformatics: parse chemical SMILES representations, compute molecular descriptors, and query bioactivity databases."
author: Nous Research / Hermes Science
version: 1.0.0
license: MIT
metadata:
  category: research
  skills: [drug_discovery, cheminformatics, smiles, molecular_biology, bioactivity]
  risk_level: low
parameters:
  smiles_string:
    type: string
    description: Simplified molecular-input line-entry system (SMILES) chemical structure
    required: true
  target_protein:
    type: string
    description: Target receptor or protein enzyme
    required: false
  calculate_lipinski:
    type: boolean
    description: Calculate Lipinski's Rule of Five drug-likeness metrics
    default: true
---

# Drug Discovery Skill 🧬

Analyzes chemical candidates and evaluates drug-like pharmacokinetic properties.
Includes:
- Molecular weight, LogP (lipophilicity), H-bond donors/acceptors, and polar surface area (TPSA).
- Target binding affinity profiling and toxicity alert screening.
- Structural analogs and synthetic accessibility scoring.

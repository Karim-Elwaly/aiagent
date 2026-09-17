---
name: oss_forensics
description: Forensically analyze open source packages and repositories for supply chain malware, obfuscated code, backdoor hooks, and tampering.
author: Nous Research / Hermes Security
version: 1.2.0
license: MIT
metadata:
  category: security
  skills: [oss_forensics, malware_analysis, supply_chain_security, reverse_engineering, audit]
  risk_level: high
parameters:
  package_name:
    type: string
    description: Name or repository URL of the package to inspect
    required: true
  ecosystem:
    type: string
    description: Target package ecosystem (npm, pypi, cargo, rubygems)
    default: pypi
  deep_inspect:
    type: boolean
    description: Perform AST de-obfuscation and network outbound hook analysis
    default: true
---

# OSS Forensics Skill 🛡️

Forensically evaluates third-party packages for software supply chain risks.
Analyzes:
1. Setup/Install hook execution (`setup.py`, `postinstall.js`, `build.rs`).
2. Obfuscated eval/exec patterns, base64 payloads, and dynamic imports.
3. Outbound telemetry, credential exfiltration endpoints, and environment variable scrapers.
4. Typosquatting heuristics and maintainer anomaly scores.

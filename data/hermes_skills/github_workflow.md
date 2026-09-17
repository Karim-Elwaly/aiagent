---
name: github_workflow
description: Automate GitHub PR creation, analyze CI/CD GitHub Actions workflow runs, and generate release changelogs.
version: 1.0.0
author: nous_research
category: developer-tools
risk_level: medium
metadata:
  skills: [github_workflow, pull_requests, ci_cd_debug, release_notes]
---

# GitHub Workflow & CI/CD Automation Skill

Use this skill to interface with GitHub repositories, pull requests, actions workflows, and releases.

## Core Operations

1. **Pull Request Preparation**:
   - Write clear PR titles using Conventional Commits format (`feat:`, `fix:`, `refactor:`).
   - Generate automated markdown PR descriptions with summary of changes, motivation, and verification steps.

2. **Actions Failure Analysis**:
   - Download step logs from failed GitHub Actions jobs.
   - Isolate root causes (flaky network, dependency mismatch, missing secrets, failing unit test).
   - Propose focused fixes.

3. **Changelog Generation**:
   - Aggregate merged PRs between git tags.
   - Categorize entries into Features, Bug Fixes, Performance, and Breaking Changes.

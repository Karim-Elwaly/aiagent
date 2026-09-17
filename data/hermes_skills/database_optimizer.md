---
name: database_optimizer
description: Analyze PostgreSQL and SQLite query plans, diagnose slow sequential scans, identify missing indexes, and resolve N+1 queries.
version: 1.0.0
author: nous_research
category: database
risk_level: medium
metadata:
  skills: [database_optimizer, sql_tuning, explain_analyze, index_optimization]
---

# Database Performance & SQL Optimization Skill

Optimizes relational database queries, schema designs, and index coverage for high-throughput applications.

## Analysis Protocol

1. **Query Plan Inspection**:
   - Run `EXPLAIN (ANALYZE, BUFFERS)` on slow queries.
   - Detect sequential table scans (`Seq Scan`) on large datasets where index scans should occur.

2. **Index Strategy**:
   - Identify composite index candidates for multi-column WHERE clauses.
   - Recommend partial indexes (`WHERE active = true`) or covering indexes (`INCLUDE` clauses) to eliminate heap fetches.

3. **ORM & N+1 Query Detection**:
   - Audit ORM query patterns for redundant round-trips.
   - Recommend `select_related` / `prefetch_related` (Django) or `joinedload` (SQLAlchemy).

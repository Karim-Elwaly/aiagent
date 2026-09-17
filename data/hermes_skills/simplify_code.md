---
name: simplify_code
description: Refactor convoluted functions, eliminate redundant abstractions, reduce cyclomatic complexity, and improve readability.
version: 1.0.0
author: nous_research
category: software-development
risk_level: low
metadata:
  skills: [simplify_code, code_refactoring, clean_code, complexity_reduction]
---

# Code Simplification & Refactoring Skill

This skill enforces clarity and idiomatic structure across codebases while maintaining complete functional equivalence.

## Core Directives

1. **Reduce Nesting**:
   - Invert `if` conditions to return early (guard clauses).
   - Flatten nested ternary and comprehension blocks.
   
2. **Eliminate Redundant Code**:
   - Remove dead branches, unused variables, and verbose boilerplate.
   - Replace complex manual loops with standard library built-ins (`itertools`, `collections`, modern stdlib).

3. **Verify Equivalence**:
   - Run existing unit tests before and after the modification using `execute_code`.
   - Never remove type annotations, docstrings, or public interface contracts.

4. **Diff Delivery**:
   Use `patch_file` to execute surgical diffs without destroying whitespace or unrelated comments.

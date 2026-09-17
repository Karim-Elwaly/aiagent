---
name: docker_ops
description: Inspect running containers, debug failing builds, optimize Dockerfile layers, and orchestrate Docker Compose stacks.
version: 1.0.0
author: nous_research
category: devops
risk_level: high
metadata:
  skills: [docker_ops, container_management, docker_compose, devops_troubleshooting]
---

# Docker Operations & Containerization Skill

Enables the agent to diagnose container failures, streamline multi-stage builds, and audit container security.

## Best Practices

1. **Layer Optimization**:
   - Order Dockerfile instructions from least frequently changed to most frequently changed.
   - Leverage multi-stage builds to exclude build tools and dev dependencies from final images.
   
2. **Health Diagnostics**:
   - Inspect container logs and exited exit codes (`docker inspect`, `docker logs --tail 100`).
   - Audit mounted volumes and exposed network ports for security vulnerabilities.

3. **Orchestration**:
   - Validate `compose.yaml` syntax, environment variable substitution, and service dependency ordering (`depends_on: condition: service_healthy`).

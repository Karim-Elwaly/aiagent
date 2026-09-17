# UAOS Algorithmic Specifications Reference

The complete, authoritative Algorithmic Specifications Document has been published to:
👉 [**`docs/ALGORITHMS.md`**](docs/ALGORITHMS.md)

### Summary Table of Contents
1. **Mathematical Formalism of the UAOS Engine**
   - Formal tuple $\mathcal{M} = \langle Q, \mathcal{S}, \mathcal{T}, \mathcal{G}, \Omega \rangle$
2. **Algorithm 1: Dynamic TaskDAG Decomposition & Cycle Validation**
   - Kahn's algorithm for topological sorting & cycle detection: $\mathcal{O}(|V| + |E|)$
3. **Algorithm 2: Durable DAG Routing & Deadlock Resolution**
   - Dynamic ready task selection: $V_{\text{ready}} = \{ v \in V \setminus (C \cup F) \mid \text{Pred}(v) \subseteq C \}$
   - Deadlock detection & Meta-Planner re-planning condition
4. **Algorithm 3: Guarded ReAct State Machine (with 5 Reliability Guardrails)**
   - Finite state machine: $\text{THINK} \to \text{ACT} \to \text{OBSERVE} \to \text{EVALUATE}$
   - Iteration threshold $K_{\max} = 10$
   - Hallucination intercept feedback loop
   - Output truncation function $\tau(O)$
   - Implicit final answer recovery heuristic
5. **Algorithm 4: Greedy Skill-to-Tool Resolution**
   - Weighted set-cover approximation with inverted skill index: $\mathcal{O}(|S_{\text{req}}|)$
6. **Algorithm 5: Real-Time Event Bus with Circular Ring Buffer**
   - Producer-consumer fan-out with bounded history replay ($C = 500$)
7. **Algorithm 6: Interactive HITL Escalation Race Condition**
   - Temporal Signal wait condition racing against timer $\Delta t_{\text{esc}}$

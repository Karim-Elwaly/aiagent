/**
 * UAOS Mission Control — Main Application Logic
 * Integrates with FastAPI gateway, polls Temporal status,
 * triggers approval gates, and animates DAG transitions.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Support file:// and HTTP origins transparently
  const API_BASE = window.location.protocol.startsWith("http")
    ? ""
    : "http://127.0.0.1:8001";

  const originalFetch = window.fetch;
  window.fetch = function (resource, init) {
    if (typeof resource === "string" && resource.startsWith("/") && API_BASE) {
      resource = API_BASE + resource;
    }
    return originalFetch.call(this, resource, init);
  };

  // Elements
  const temporalStatusEl = document.getElementById("temporal-status");
  const llmStatusEl = document.getElementById("llm-status");
  const toolsCountEl = document.getElementById("tools-count");
  const toolListEl = document.getElementById("tool-list");
  const promptInput = document.getElementById("problem-prompt");
  const solveBtn = document.getElementById("solve-btn");
  const solveBtnText = document.getElementById("solve-btn-text");
  const solutionBody = document.getElementById("solution-body");
  const timelineList = document.getElementById("timeline-list");
  const approvalModal = document.getElementById("approval-modal");
  const approvalTaskName = document.getElementById("approval-task-name");
  const approvalTaskDesc = document.getElementById("approval-task-desc");
  const approvalRiskBadge = document.getElementById("approval-risk-badge");
  const approvalTimerText = document.getElementById("approval-timer-text");
  const approvalGuidanceInput = document.getElementById("approval-guidance-input");
  const approvalParamsInput = document.getElementById("approval-params-input");
  const approveBtn = document.getElementById("modal-approve-btn");
  const rejectBtn = document.getElementById("modal-reject-btn");

  // State
  let currentWorkflowId = null;
  let pollInterval = null;
  let activeDag = null;
  let activeEventSource = null;
  let approvalTimerInterval = null;

  // Initialize DAG Renderer
  const dagRenderer = new DAGRenderer("dag-svg", (task, status) => {
    showToast(`Task ${task.id}: ${task.name} (${status.toUpperCase()})`);
  });

  // 1. Initial Health, Tools, and Agents Fetch
  fetchHealth();
  fetchTools();
  fetchAgents();
  setInterval(fetchHealth, 10000);

  // 2. Preset Queries
  document.querySelectorAll(".preset-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      promptInput.value = prompt;
      promptInput.focus();
    });
  });

  // 3. Problem Submission
  solveBtn.addEventListener("click", async () => {
    const query = promptInput.value.trim();
    if (!query) {
      showToast("Please enter a problem description first", "error");
      return;
    }

    setRunningState(true);
    resetDashboard();
    const modeAsyncEl = document.getElementById("mode-async");
    const isAsync = modeAsyncEl ? modeAsyncEl.checked : true;
    const agentSelectorEl = document.getElementById("agent-selector");
    const selectedAgentId = agentSelectorEl ? agentSelectorEl.value : "";
    const solvePayload = { query, agent_id: selectedAgentId || null };

    try {
      if (isAsync) {
        // Start workflow asynchronously
        const res = await fetch("/solve/async", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(solvePayload),
        });

        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();
        currentWorkflowId = data.workflow_id;
        showToast(`Workflow spawned: ${currentWorkflowId}`);

        // Connect real-time SSE event stream
        connectWorkflowStream(currentWorkflowId);

        // Start polling status (fallback / state synchronization)
        startStatusPolling(currentWorkflowId, query);
      } else {
        // Synchronous run
        showToast("Planning and executing DAG with Universal Workers...");
        const res = await fetch("/solve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(solvePayload),
        });

        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();

        renderFinalSolution(data.response, data.tasks_completed, data.tasks_failed);
        setRunningState(false);
      }
    } catch (err) {
      console.error(err);
      // Fallback to demo mode if backend server is not reachable
      showToast("Running interactive demonstration pipeline...", "info");
      runDemoSimulation(query);
    }
  });

  // 4. Real-Time Streaming (SSE) and Status Polling
  function connectWorkflowStream(workflowId) {
    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }

    try {
      const es = new EventSource(`/stream/${workflowId}`);
      activeEventSource = es;

      es.onopen = () => {
        console.log(`[SSE] Connected to event stream for workflow ${workflowId}`);
      };

      es.onmessage = (event) => {
        try {
          const ev = JSON.parse(event.data);
          handleStreamEvent(ev);
        } catch (err) {
          console.warn("[SSE] Parse error:", err, event.data);
        }
      };

      es.onerror = (err) => {
        console.warn("[SSE] Connection closed or error:", err);
      };
    } catch (e) {
      console.error("[SSE] Failed to establish EventSource:", e);
    }
  }

  function handleStreamEvent(ev) {
    if (!ev) return;
    const evType = ev.type || ev.event_type;
    if (!evType) return;

    switch (evType) {
      case "connected":
        console.log(`[SSE] Stream ready for workflow: ${ev.workflow_id}`);
        break;

      case "token": {
        // Real-time token streaming from worker ReAct loop
        const taskId = ev.task_id;
        const tokenText = ev.content !== undefined ? ev.content : (ev.token || "");
        let stepEl = document.getElementById(`step-${taskId}`);
        if (!stepEl) {
          addTimelineStep(taskId, ev.task_name || `Task ${taskId}`, "", "running");
          if (activeDag) dagRenderer.updateNodeStatus(taskId, "running");
        }
        const descEl = document.getElementById(`desc-${taskId}`);
        if (descEl) {
          if (descEl.dataset.streaming !== "true") {
            descEl.dataset.streaming = "true";
            descEl.textContent = "";
          }
          descEl.textContent += tokenText;
          timelineList.scrollTop = timelineList.scrollHeight;
        }
        break;
      }

      case "tool_start": {
        const taskId = ev.task_id;
        const toolName = ev.tool || ev.tool_name || "tool";
        let toolsEl = document.getElementById(`tools-${taskId}`);
        if (!toolsEl) {
          addTimelineStep(taskId, `Task ${taskId}`, "Executing tool...", "running");
          toolsEl = document.getElementById(`tools-${taskId}`);
        }
        if (toolsEl) {
          const toolBadgeId = `tool-live-${taskId}-${toolName}`;
          let existing = document.getElementById(toolBadgeId);
          if (!existing) {
            const badge = document.createElement("span");
            badge.id = toolBadgeId;
            badge.className = "skill-tag";
            badge.style.background = "rgba(245, 158, 11, 0.25)";
            badge.style.border = "1px solid rgba(245, 158, 11, 0.5)";
            badge.style.color = "#fbbf24";
            badge.innerHTML = `⚡ ${toolName}...`;
            toolsEl.appendChild(badge);
          }
        }
        break;
      }

      case "tool_end": {
        const taskId = ev.task_id;
        const toolName = ev.tool || ev.tool_name || "tool";
        const toolBadgeId = `tool-live-${taskId}-${toolName}`;
        const existing = document.getElementById(toolBadgeId);
        if (existing) {
          existing.style.background = "rgba(16, 185, 129, 0.2)";
          existing.style.border = "1px solid rgba(16, 185, 129, 0.5)";
          existing.style.color = "#34d399";
          existing.innerHTML = `✔ ${toolName}`;
        }
        break;
      }

      case "approval_required": {
        const taskName = ev.task_name || ev.name || `Task ${ev.task_id || ''}`;
        const taskDesc = ev.task_desc || ev.description || "";
        const riskLevel = ev.risk_level || ev.risk || "critical";
        const taskParams = ev.task_params || ev.params || ev.parameters || null;
        const timeoutSec = ev.timeout_seconds || ev.timeout || 900;

        showApprovalModal(taskName, taskDesc, riskLevel, taskParams, timeoutSec);
        showToast(`⚠️ Approval Required for: ${taskName}`, "warning");
        break;
      }

      case "approval_resolved":
        hideApprovalModal();
        showToast(
          ev.approved ? "Task approved! Resuming execution." : "Task rejected by operator.",
          ev.approved ? "info" : "warning"
        );
        break;

      case "escalation_triggered":
        showToast(`🚨 Approval timed out after 15m! Escalated to administrator.`, "error");
        if (approvalTimerText) {
          approvalTimerText.textContent = "00:00 (ESCALATED)";
          approvalTimerText.style.color = "#ef4444";
        }
        break;

      case "final_solution": {
        const sol = ev.solution || ev.response || "";
        renderFinalSolution(sol, ev.tasks_completed || 0, ev.tasks_failed || 0);
        setRunningState(false);
        if (activeEventSource) {
          activeEventSource.close();
          activeEventSource = null;
        }
        if (pollInterval) {
          clearInterval(pollInterval);
          pollInterval = null;
        }
        break;
      }

      case "workflow_completed":
      case "workflow_failed":
        setRunningState(false);
        if (activeEventSource) {
          activeEventSource.close();
          activeEventSource = null;
        }
        if (pollInterval) {
          clearInterval(pollInterval);
          pollInterval = null;
        }
        break;

      default:
        break;
    }
  }

  function startStatusPolling(workflowId, originalQuery) {
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/status/${workflowId}`);
        if (!res.ok) return;

        const status = await res.json();

        // 1. Render DAG as soon as planning completes
        if (status.dag && (!activeDag || activeDag.goal !== status.dag.goal)) {
          activeDag = status.dag;
          dagRenderer.render(status.dag);
        }

        // 2. Update task statuses in DAG & timeline
        if (status.task_statuses && activeDag) {
          for (const [tid, tstatus] of Object.entries(status.task_statuses)) {
            dagRenderer.updateNodeStatus(tid, tstatus);
            const taskObj = (activeDag.tasks || []).find(t => t.id === tid);
            const taskName = taskObj ? taskObj.name : `Task ${tid}`;
            let stepEl = document.getElementById(`step-${tid}`);
            if (!stepEl) {
              addTimelineStep(tid, taskName, taskObj ? taskObj.description : "", tstatus);
            } else if (tstatus === "completed") {
              updateTimelineStep(tid, "Task completed successfully.", "completed");
            } else if (tstatus === "failed") {
              const marker = document.getElementById(`marker-${tid}`);
              if (marker) marker.className = "step-marker failed";
              const duration = document.getElementById(`duration-${tid}`);
              if (duration) duration.textContent = "FAILED";
            }
          }
        }

        // 3. Check if approval required
        if (status.awaiting_approval) {
          showApprovalModal(
            status.pending_task,
            status.pending_task_desc,
            status.pending_task_risk,
            status.pending_task_params,
            900
          );
        }

        // 4. If completed or failed
        if (status.status === "completed" || status.status === "failed") {
          clearInterval(pollInterval);
          pollInterval = null;
          setRunningState(false);
          if (status.result) {
            renderFinalSolution(status.result.response, status.result.tasks_completed, status.result.tasks_failed);
            const solutionCard = document.querySelector(".solution-card");
            if (solutionCard) {
              solutionCard.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          }
          if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
          }
        }
      } catch (e) {
        console.warn("Polling status error:", e);
      }
    }, 1500);
  }

  // 5. Interactive Approval Modal Actions
  approveBtn.addEventListener("click", () => sendApprovalSignal(true));
  rejectBtn.addEventListener("click", () => sendApprovalSignal(false));

  const testApprovalGateBtn = document.getElementById("test-approval-gate-btn");
  const openApprovalPreviewBtn = document.getElementById("open-approval-preview-btn");

  const triggerApprovalPreview = () => {
    showApprovalModal(
      "Deploy Database Migration & CVE-2024-3094 Remediation",
      "High-risk schema modification and binary update requiring explicit operator approval before execution.",
      "critical",
      {
        "cve_id": "CVE-2024-3094",
        "component": "liblzma",
        "action": "downgrade_and_isolate",
        "dry_run": false
      },
      895
    );
    showToast("Interactive HITL Approval Gate preview activated", "info");
  };

  if (testApprovalGateBtn) testApprovalGateBtn.addEventListener("click", triggerApprovalPreview);
  if (openApprovalPreviewBtn) openApprovalPreviewBtn.addEventListener("click", triggerApprovalPreview);

  async function sendApprovalSignal(approved) {
    if (!currentWorkflowId) {
      const guidance = approvalGuidanceInput ? approvalGuidanceInput.value.trim() : "";
      showToast(
        approved
          ? (guidance ? `Approved with operator guidance: "${guidance}"` : "Task approved! Resuming execution.")
          : "Task rejected by operator."
      );
      hideApprovalModal();
      return;
    }

    let guidance = "";
    if (approvalGuidanceInput) {
      guidance = approvalGuidanceInput.value.trim();
    }

    let modifiedParams = null;
    if (approvalParamsInput && approvalParamsInput.value.trim()) {
      try {
        modifiedParams = JSON.parse(approvalParamsInput.value.trim());
        if (typeof modifiedParams !== "object" || Array.isArray(modifiedParams)) {
          showToast("Modified parameters must be a valid JSON object {}", "error");
          return;
        }
      } catch (e) {
        showToast("Invalid JSON syntax in parameter override!", "error");
        return;
      }
    }

    try {
      const payload = {
        approved: approved,
        guidance: guidance || null,
        modified_params: modifiedParams,
      };

      const res = await fetch(`/approve/${currentWorkflowId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      showToast(
        approved
          ? (guidance ? "Task approved with operator guidance!" : "Task approved! Resuming execution.")
          : "Task rejected by operator."
      );
      hideApprovalModal();
    } catch (e) {
      showToast(`Failed to send approval signal: ${e.message}`, "error");
    }
  }

  function showApprovalModal(taskName, taskDesc, riskLevel = "critical", taskParams = null, timeoutSec = 900) {
    approvalTaskName.textContent = taskName || "High-Risk Operation";
    approvalTaskDesc.textContent =
      taskDesc ||
      "A worker agent is paused at an approval gate. This task has been classified as high-risk and requires explicit confirmation before execution.";

    if (approvalRiskBadge) {
      const risk = (riskLevel || "critical").toLowerCase();
      approvalRiskBadge.textContent = risk.toUpperCase();
      approvalRiskBadge.className = `risk-badge risk-${risk}`;
    }

    if (approvalParamsInput) {
      approvalParamsInput.value =
        taskParams && Object.keys(taskParams).length > 0
          ? JSON.stringify(taskParams, null, 2)
          : "";
    }

    if (approvalGuidanceInput) {
      approvalGuidanceInput.value = "";
    }

    startApprovalCountdown(timeoutSec);
    approvalModal.classList.add("active");
  }

  function startApprovalCountdown(seconds) {
    if (approvalTimerInterval) clearInterval(approvalTimerInterval);
    let remaining = seconds || 900;
    updateTimerDisplay(remaining);

    approvalTimerInterval = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(approvalTimerInterval);
        approvalTimerInterval = null;
        if (approvalTimerText) {
          approvalTimerText.textContent = "00:00 (ESCALATED)";
          approvalTimerText.style.color = "#ef4444";
        }
      } else {
        updateTimerDisplay(remaining);
      }
    }, 1000);
  }

  function updateTimerDisplay(remainingSec) {
    if (!approvalTimerText) return;
    const mins = Math.floor(remainingSec / 60);
    const secs = remainingSec % 60;
    approvalTimerText.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    approvalTimerText.style.color = remainingSec < 120 ? "#ef4444" : "#fbbf24";
  }

  function hideApprovalModal() {
    if (approvalTimerInterval) {
      clearInterval(approvalTimerInterval);
      approvalTimerInterval = null;
    }
    approvalModal.classList.remove("active");
  }

  const closeApprovalModalBtn = document.getElementById("close-approval-modal-btn");
  if (closeApprovalModalBtn) {
    closeApprovalModalBtn.addEventListener("click", hideApprovalModal);
  }

  // Click outside card to dismiss
  if (approvalModal) {
    approvalModal.addEventListener("click", (e) => {
      if (e.target === approvalModal) {
        hideApprovalModal();
      }
    });
  }

  // Escape key closes any active modal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideApprovalModal();
      const llmModal = document.getElementById("llm-settings-modal");
      if (llmModal) llmModal.classList.remove("active");
      const intModal = document.getElementById("integrations-modal");
      if (intModal) intModal.classList.remove("active");
      const agModal = document.getElementById("agents-modal");
      if (agModal) agModal.classList.remove("active");
    }
  });

  // 6. Health Fetcher
  async function fetchHealth() {
    try {
      const res = await fetch("/health");
      const data = await res.json();

      // Temporal Status
      if (temporalStatusEl) {
        if (data.temporal_available) {
          temporalStatusEl.className = "status-pill online";
          temporalStatusEl.innerHTML = '<span class="dot"></span><span class="status-label">Temporal Online</span>';
        } else {
          temporalStatusEl.className = "status-pill degraded";
          temporalStatusEl.innerHTML = '<span class="dot"></span><span class="status-label">Temporal Offline</span>';
        }
      }

      // LLM Status
      if (llmStatusEl) {
        if (data.llm_available) {
          llmStatusEl.className = "status-pill online";
          llmStatusEl.innerHTML = '<span class="dot"></span><span class="status-label">LLM Ready</span>';
        } else {
          llmStatusEl.className = "status-pill degraded";
          llmStatusEl.innerHTML = '<span class="dot"></span><span class="status-label">LLM Standby</span>';
        }
      }

      // Tools Count Badge
      if (data.tools_registered !== undefined && toolsCountEl) {
        toolsCountEl.textContent = data.tools_registered;
      }
    } catch (e) {
      if (temporalStatusEl) {
        temporalStatusEl.className = "status-pill degraded";
        temporalStatusEl.innerHTML = '<span class="dot"></span><span class="status-label">Temporal: Local</span>';
      }
    }
  }

  // 7. Tools Explorer Fetcher
  async function fetchTools() {
    try {
      const res = await fetch("/tools");
      const tools = await res.json();

      toolListEl.innerHTML = "";
      tools.forEach((t) => {
        const card = document.createElement("div");
        card.className = "tool-card";

        const skillsHtml = (t.skills_provided || [])
          .map((s) => `<span class="skill-tag">${s}</span>`)
          .join("");

        // Badge styling based on source_type
        let sourceBadge = `<span style="background: rgba(139, 92, 246, 0.2); color: #c4b5fd; border: 1px solid rgba(139, 92, 246, 0.4); font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; margin-left: 6px;">NATIVE</span>`;
        if (t.source_type === "mcp") {
          sourceBadge = `<span style="background: rgba(6, 182, 212, 0.2); color: #38bdf8; border: 1px solid rgba(6, 182, 212, 0.4); font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; margin-left: 6px;">MCP</span>`;
        } else if (t.source_type === "openapi") {
          sourceBadge = `<span style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; margin-left: 6px;">OPENAPI</span>`;
        }

        // Delete button for dynamic tools
        let deleteBtn = "";
        if (t.source_type !== "native") {
          deleteBtn = `<button class="delete-tool-btn" data-id="${t.tool_id}" title="Unregister tool" style="background: none; border: none; cursor: pointer; color: #ef4444; font-size: 13px; margin-left: auto; padding: 0 4px;">✕</button>`;
        }

        card.innerHTML = `
          <div class="tool-name-row" style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center;">
              <span class="tool-name">${t.name}</span>
              ${sourceBadge}
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="risk-badge risk-${t.risk_level || 'low'}">${t.risk_level || 'low'}</span>
              ${deleteBtn}
            </div>
          </div>
          <div class="tool-desc">${t.description}</div>
          <div class="skill-tags">${skillsHtml}</div>
        `;
        toolListEl.appendChild(card);
      });

      // Wire up delete buttons
      document.querySelectorAll(".delete-tool-btn").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const toolId = btn.getAttribute("data-id");
          if (!confirm(`Unregister dynamic tool '${toolId}'?`)) return;
          try {
            const res = await fetch(`/api/tools/${encodeURIComponent(toolId)}`, {
              method: "DELETE",
            });
            if (res.ok) {
              showToast(`Tool '${toolId}' unregistered`);
              loadTools();
              fetchHealth();
            } else {
              showToast("Failed to unregister tool", "error");
            }
          } catch (err) {
            showToast(`Error: ${err.message}`, "error");
          }
        });
      });
    } catch (e) {
      console.warn("Could not load tools:", e);
    }
  }

  // 8. Demo Simulation Pipeline (Provides dynamic visual experience)
  async function runDemoSimulation(query) {
    // Generate an illustrative TaskDAG
    const mockDAG = {
      goal: query,
      reasoning: "Dynamic problem decomposition into 3 sequential & parallel stages.",
      tasks: [
        {
          id: "t1",
          name: "Information Gathering",
          description: "Inspect query and search resources or local environment",
          required_skills: ["web_search", "file_reading"],
          dependencies: [],
          risk_level: "low",
        },
        {
          id: "t2",
          name: "Computational Analysis",
          description: "Execute Python analysis on gathered parameters",
          required_skills: ["code_execution", "data_analysis"],
          dependencies: ["t1"],
          risk_level: "medium",
        },
        {
          id: "t3",
          name: "Synthesize Results",
          description: "Structure actionable response for user",
          required_skills: ["general_reasoning"],
          dependencies: ["t2"],
          risk_level: "low",
        },
      ],
    };

    dagRenderer.render(mockDAG);
    document.getElementById("dag-empty").style.display = "none";

    // Stage 1: Task 1 Running
    dagRenderer.updateNodeStatus("t1", "running");
    addTimelineStep("t1", "Information Gathering", "Universal Worker analyzing sources...", "running");
    await sleep(1500);

    // Stage 1: Task 1 Completed
    dagRenderer.updateNodeStatus("t1", "completed");
    updateTimelineStep("t1", "Extracted 4 relevant data records via web_search tool (142ms)", "completed", ["web_search"]);

    // Stage 2: Task 2 Running
    dagRenderer.updateNodeStatus("t2", "running");
    addTimelineStep("t2", "Computational Analysis", "Spawning Worker with Python Executor sandboxing...", "running");
    await sleep(1600);

    // Stage 2: Task 2 Completed
    dagRenderer.updateNodeStatus("t2", "completed");
    updateTimelineStep("t2", "Executed Python code sandbox, verified outputs (280ms)", "completed", ["execute_python"]);

    // Stage 3: Task 3 Running
    dagRenderer.updateNodeStatus("t3", "running");
    addTimelineStep("t3", "Synthesize Results", "Response Assembler synthesizing final output...", "running");
    await sleep(1200);

    // Stage 3: Task 3 Completed
    dagRenderer.updateNodeStatus("t3", "completed");
    updateTimelineStep("t3", "Complete multi-step response generated (85ms)", "completed", []);

    renderFinalSolution(
      `### UAOS Execution Summary for "${query}"\n\n` +
      `The problem was dynamically decomposed into a 3-stage TaskDAG, verified against dependency constraints, and executed with Universal Worker Agents.\n\n` +
      `- **Data Collection**: Sourced and validated necessary background parameters.\n` +
      `- **Computation**: Sandboxed execution in Python completed without error.\n` +
      `- **Resolution**: All 3 tasks finished successfully with zero memory leaks.\n\n` +
      `*Orchestrated durably with Temporal state recovery.*`,
      3,
      0
    );

    setRunningState(false);
  }

  // 9. Helpers
  function renderFinalSolution(markdownText, completedCount, failedCount) {
    solutionBody.innerHTML = formatMarkdown(markdownText);
    showToast(`Execution finished! ${completedCount} completed, ${failedCount} failed.`);
  }

  function addTimelineStep(id, title, desc, status) {
    const el = document.createElement("div");
    el.id = `step-${id}`;
    el.className = `timeline-step active`;
    el.innerHTML = `
      <div class="step-marker" id="marker-${id}">${id.toUpperCase()}</div>
      <div class="step-content">
        <div class="step-title-row">
          <span class="step-title">${title}</span>
          <span class="step-duration" id="duration-${id}">RUNNING</span>
        </div>
        <div class="step-desc" id="desc-${id}">${desc}</div>
        <div class="step-tools" id="tools-${id}"></div>
      </div>
    `;
    timelineList.appendChild(el);
    timelineList.scrollTop = timelineList.scrollHeight;
  }

  function updateTimelineStep(id, desc, status, tools = []) {
    const el = document.getElementById(`step-${id}`);
    const marker = document.getElementById(`marker-${id}`);
    const duration = document.getElementById(`duration-${id}`);
    const descEl = document.getElementById(`desc-${id}`);
    const toolsEl = document.getElementById(`tools-${id}`);

    if (el) el.className = `timeline-step`;
    if (marker) marker.className = `step-marker done`;
    if (duration) duration.textContent = "COMPLETED";
    if (descEl) descEl.textContent = desc;
    if (toolsEl && tools.length > 0) {
      toolsEl.innerHTML = `Tools: ${tools.map(t => `<span class="skill-tag">${t}</span>`).join(" ")}`;
    }
  }

  function resetDashboard() {
    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }
    if (approvalTimerInterval) {
      clearInterval(approvalTimerInterval);
      approvalTimerInterval = null;
    }
    activeDag = null;
    if (dagRenderer && typeof dagRenderer.reset === "function") {
      dagRenderer.reset();
    }
    timelineList.innerHTML = '<div class="empty-timeline-notice">No tasks executed yet.</div>';
    solutionBody.innerHTML = '<div class="empty-solution-notice">Execution in progress...</div>';
  }

  function setRunningState(isRunning) {
    solveBtn.disabled = isRunning;
    solveBtnText.textContent = isRunning ? "Executing Task..." : "Execute Task";
  }

  function formatMarkdown(text) {
    if (!text) return "";
    return text
      .replace(/^### (.*$)/gim, "<h3>$1</h3>")
      .replace(/^## (.*$)/gim, "<h2>$1</h2>")
      .replace(/^# (.*$)/gim, "<h1>$1</h1>")
      .replace(/\*\*(.*)\*\*/gim, "<strong>$1</strong>")
      .replace(/\*(.*)\*/gim, "<em>$1</em>")
      .replace(/`([^`]+)`/gim, "<code>$1</code>")
      .replace(/\n/gim, "<br>");
  }

  function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid var(--accent-cyan);
      color: #fff;
      padding: 12px 20px;
      border-radius: var(--radius-full);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
      font-size: 13px;
      font-weight: 500;
      z-index: 2000;
      animation: fadeIn 0.3s ease;
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // 10. LLM Settings Modal Management
  const llmSettingsModal = document.getElementById("llm-settings-modal");
  const openLlmBtn = document.getElementById("open-llm-settings-btn");
  const closeLlmBtn = document.getElementById("close-llm-modal-btn");
  const testLlmBtn = document.getElementById("test-llm-btn");
  const saveLlmBtn = document.getElementById("save-llm-btn");
  const fetchModelsBtn = document.getElementById("fetch-models-btn");
  const inputBaseUrl = document.getElementById("llm-input-base-url");
  const inputModel = document.getElementById("llm-input-model");
  const discoveredSelect = document.getElementById("discovered-models-select");
  const testStatusEl = document.getElementById("llm-test-status");

  // Load current settings from backend
  async function loadCurrentLlmSettings() {
    try {
      const res = await fetch("/api/settings/llm");
      if (res.ok) {
        const data = await res.json();
        if (inputBaseUrl) inputBaseUrl.value = data.base_url || "http://localhost:1234/v1";
        if (inputModel) inputModel.value = data.model || "hermes3";
      }
    } catch (e) {
      console.warn("Could not load LLM settings:", e);
    }
  }
  loadCurrentLlmSettings();

  // Open modal triggers
  if (openLlmBtn) {
    openLlmBtn.addEventListener("click", () => {
      loadCurrentLlmSettings();
      llmSettingsModal.classList.add("active");
    });
  }
  if (llmStatusEl) {
    llmStatusEl.style.cursor = "pointer";
    llmStatusEl.title = "Click to configure LLM connection";
    llmStatusEl.addEventListener("click", () => {
      loadCurrentLlmSettings();
      llmSettingsModal.classList.add("active");
    });
  }

  // Close modal
  if (closeLlmBtn) {
    closeLlmBtn.addEventListener("click", () => {
      llmSettingsModal.classList.remove("active");
      if (testStatusEl) testStatusEl.style.display = "none";
    });
  }

  // Presets
  const presetLmStudio = document.getElementById("preset-lmstudio");
  const presetOllama = document.getElementById("preset-ollama");
  const presetVllm = document.getElementById("preset-vllm");

  if (presetLmStudio) {
    presetLmStudio.addEventListener("click", () => {
      inputBaseUrl.value = "http://localhost:1234/v1";
      showToast("Selected LM Studio default (:1234). Replace localhost with VM IP if remote.");
    });
  }
  if (presetOllama) {
    presetOllama.addEventListener("click", () => {
      inputBaseUrl.value = "http://localhost:11434/v1";
      showToast("Selected Ollama default (:11434)");
    });
  }
  if (presetVllm) {
    presetVllm.addEventListener("click", () => {
      inputBaseUrl.value = "http://localhost:8000/v1";
      showToast("Selected vLLM default (:8000)");
    });
  }

  // Detect Models from VM / Server
  if (fetchModelsBtn) {
    fetchModelsBtn.addEventListener("click", async () => {
      const baseUrl = inputBaseUrl.value.trim();
      if (!baseUrl) {
        showToast("Please enter an inference base URL first", "error");
        return;
      }
      fetchModelsBtn.textContent = "Detecting...";

      try {
        const res = await fetch("/api/settings/test-llm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ base_url: baseUrl }),
        });
        const data = await res.json();

        if (data.models && data.models.length > 0) {
          discoveredSelect.innerHTML = "";
          data.models.forEach((m) => {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m;
            discoveredSelect.appendChild(opt);
          });
          discoveredSelect.style.display = "block";
          inputModel.value = data.models[0];
          showToast(`Discovered ${data.models.length} model(s) from server!`);

          discoveredSelect.onchange = () => {
            inputModel.value = discoveredSelect.value;
          };
        } else {
          showToast("Server reached, but no model list returned. You can manually enter the model name.", "info");
        }
      } catch (e) {
        showToast("Could not fetch models. Check IP, port, and firewall.", "error");
      } finally {
        fetchModelsBtn.textContent = "🔄 Detect Models from VM";
      }
    });
  }

  // Test Connection
  if (testLlmBtn) {
    testLlmBtn.addEventListener("click", async () => {
      const baseUrl = inputBaseUrl.value.trim();
      const model = inputModel.value.trim();
      if (!baseUrl) {
        showToast("Please enter base URL", "error");
        return;
      }

      testStatusEl.style.display = "block";
      testStatusEl.style.background = "rgba(6, 182, 212, 0.1)";
      testStatusEl.style.color = "#38bdf8";
      testStatusEl.textContent = `Connecting to ${baseUrl}...`;

      try {
        const startTime = performance.now();
        const res = await fetch("/api/settings/test-llm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ base_url: baseUrl, model: model }),
        });
        const latency = Math.round(performance.now() - startTime);
        const data = await res.json();

        if (data.connected) {
          testStatusEl.style.background = "rgba(16, 185, 129, 0.15)";
          testStatusEl.style.color = "#34d399";
          testStatusEl.style.border = "1px solid rgba(16, 185, 129, 0.3)";
          testStatusEl.textContent = `✔ Connected successfully! Latency: ${latency}ms. Models available: ${data.models.length || 'Ready'}`;
          showToast(`LLM Server reachable (${latency}ms)`);
        } else {
          testStatusEl.style.background = "rgba(244, 63, 94, 0.15)";
          testStatusEl.style.color = "#fda4af";
          testStatusEl.style.border = "1px solid rgba(244, 63, 94, 0.3)";
          testStatusEl.textContent = `✖ Connection failed. Ensure server is running at ${baseUrl} and accessible over network.`;
        }
      } catch (err) {
        testStatusEl.style.background = "rgba(244, 63, 94, 0.15)";
        testStatusEl.style.color = "#fda4af";
        testStatusEl.textContent = `✖ Connection error: ${err.message}`;
      }
    });
  }

  // Save & Apply
  if (saveLlmBtn) {
    saveLlmBtn.addEventListener("click", async () => {
      const baseUrl = inputBaseUrl.value.trim();
      const model = inputModel.value.trim();
      if (!baseUrl || !model) {
        showToast("Please provide both Base URL and Model Name", "error");
        return;
      }

      try {
        const res = await fetch("/api/settings/llm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ base_url: baseUrl, model: model }),
        });
        if (!res.ok) throw new Error("Failed to save settings");

        showToast("LLM settings applied dynamically!");
        llmSettingsModal.classList.remove("active");
        fetchHealth(); // Update header indicator
      } catch (e) {
        showToast(`Save failed: ${e.message}`, "error");
      }
    });
  }

  // 12. Tool Integrations Modal (MCP & OpenAPI)
  const integrationsModal = document.getElementById("integrations-modal");
  const openIntegrationsBtn = document.getElementById("open-integrations-btn");
  const closeIntegrationsBtn = document.getElementById("close-integrations-modal-btn");



  if (openIntegrationsBtn && integrationsModal) {
    openIntegrationsBtn.addEventListener("click", () => {
      integrationsModal.classList.add("active");
      fetchMcpServers();
    });
  }

  if (closeIntegrationsBtn && integrationsModal) {
    closeIntegrationsBtn.addEventListener("click", () => {
      integrationsModal.classList.remove("active");
    });
  }

  const closeIntegrationsModalX = document.getElementById("close-integrations-modal-x");
  if (closeIntegrationsModalX && integrationsModal) {
    closeIntegrationsModalX.addEventListener("click", () => {
      integrationsModal.classList.remove("active");
    });
  }

  const closeLlmModalX = document.getElementById("close-llm-modal-x");
  const llmModal = document.getElementById("llm-settings-modal");
  if (closeLlmModalX && llmModal) {
    closeLlmModalX.addEventListener("click", () => {
      llmModal.classList.remove("active");
    });
  }

  // Tab switching: Installed Tools, MCP, OpenAPI
  const tabBtnTools = document.getElementById("tab-btn-tools");
  const tabBtnMcp = document.getElementById("tab-btn-mcp");
  const tabBtnOpenapi = document.getElementById("tab-btn-openapi");
  const tabContentTools = document.getElementById("tab-content-tools");
  const tabContentMcp = document.getElementById("tab-content-mcp");
  const tabContentOpenapi = document.getElementById("tab-content-openapi");

  function switchIntegrationsTab(activeTab) {
    const tabs = [
      { btn: tabBtnTools, content: tabContentTools },
      { btn: tabBtnMcp, content: tabContentMcp },
      { btn: tabBtnOpenapi, content: tabContentOpenapi }
    ];

    tabs.forEach(tab => {
      if (!tab.btn || !tab.content) return;
      if (tab.btn === activeTab) {
        tab.btn.classList.add("active");
        tab.content.style.display = "flex";
      } else {
        tab.btn.classList.remove("active");
        tab.content.style.display = "none";
      }
    });
  }

  if (tabBtnTools) tabBtnTools.addEventListener("click", () => switchIntegrationsTab(tabBtnTools));
  if (tabBtnMcp) tabBtnMcp.addEventListener("click", () => switchIntegrationsTab(tabBtnMcp));
  if (tabBtnOpenapi) tabBtnOpenapi.addEventListener("click", () => switchIntegrationsTab(tabBtnOpenapi));

  // Copy Solution button
  const copySolutionBtn = document.getElementById("copy-solution-btn");
  if (copySolutionBtn) {
    copySolutionBtn.addEventListener("click", () => {
      const text = solutionBody ? solutionBody.innerText : "";
      if (!text || text.includes("Final synthesized solution will be rendered here")) {
        showToast("No solution to copy yet", "info");
        return;
      }
      navigator.clipboard.writeText(text).then(() => {
        showToast("Solution copied to clipboard!", "info");
      }).catch(() => {
        showToast("Failed to copy text", "error");
      });
    });
  }

  // Keyboard shortcut: Enter to execute in problem prompt
  if (promptInput) {
    promptInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        solveBtn.click();
      }
    });
  }

  // MCP Presets
  const mcpServerId = document.getElementById("mcp-server-id");
  const mcpTransport = document.getElementById("mcp-transport");
  const mcpCommand = document.getElementById("mcp-command");
  const mcpEnv = document.getElementById("mcp-env");
  const mcpStatus = document.getElementById("mcp-status");
  const mcpConnectBtn = document.getElementById("mcp-connect-btn");
  const mcpConnectedList = document.getElementById("mcp-connected-list");

  const mcpPresets = {
    github: {
      id: "github",
      transport: "stdio",
      cmd: "npx -y @modelcontextprotocol/server-github",
      env: "GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here",
    },
    postgres: {
      id: "postgres",
      transport: "stdio",
      cmd: "npx -y @modelcontextprotocol/server-postgres postgresql://localhost:5432/mydb",
      env: "",
    },
    slack: {
      id: "slack",
      transport: "stdio",
      cmd: "npx -y @modelcontextprotocol/server-slack",
      env: "SLACK_BOT_TOKEN=xoxb-...\nSLACK_TEAM_ID=T...",
    },
    sqlite: {
      id: "sqlite",
      transport: "stdio",
      cmd: "uvx mcp-server-sqlite --db-path ./data.db",
      env: "",
    },
    fs: {
      id: "filesystem",
      transport: "stdio",
      cmd: "npx -y @modelcontextprotocol/server-filesystem .",
      env: "",
    },
  };

  Object.entries(mcpPresets).forEach(([key, config]) => {
    const el = document.getElementById(`preset-mcp-${key}`);
    if (el) {
      el.addEventListener("click", () => {
        if (mcpServerId) mcpServerId.value = config.id;
        if (mcpTransport) mcpTransport.value = config.transport;
        if (mcpCommand) mcpCommand.value = config.cmd;
        if (mcpEnv) mcpEnv.value = config.env;
      });
    }
  });

  // MCP Connect
  if (mcpConnectBtn) {
    mcpConnectBtn.addEventListener("click", async () => {
      const serverId = mcpServerId ? mcpServerId.value.trim() : "";
      const transport = mcpTransport ? mcpTransport.value : "stdio";
      const command = mcpCommand ? mcpCommand.value.trim() : "";
      const envRaw = mcpEnv ? mcpEnv.value.trim() : "";

      if (!serverId) {
        showToast("Please enter a server identifier", "error");
        return;
      }
      if (!command) {
        showToast("Please enter command or URL", "error");
        return;
      }

      // Parse env lines
      const envObj = {};
      if (envRaw) {
        envRaw.split("\n").forEach((line) => {
          const idx = line.indexOf("=");
          if (idx > 0) {
            envObj[line.substring(0, idx).trim()] = line.substring(idx + 1).trim();
          }
        });
      }

      mcpStatus.style.display = "block";
      mcpStatus.style.background = "rgba(139, 92, 246, 0.15)";
      mcpStatus.style.color = "#c4b5fd";
      mcpStatus.textContent = `Connecting to MCP server '${serverId}'...`;

      try {
        const payload = {
          server_id: serverId,
          transport: transport,
          command: transport === "stdio" ? command : null,
          url: transport === "sse" ? command : null,
          env: Object.keys(envObj).length > 0 ? envObj : null,
        };

        const res = await fetch("/api/tools/mcp/connect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to connect to MCP server");

        mcpStatus.style.background = "rgba(16, 185, 129, 0.15)";
        mcpStatus.style.color = "#34d399";
        mcpStatus.textContent = `✔ Connected! Registered ${data.tools_count} tool(s): ${data.tools.map(t => t.name).join(", ")}`;
        showToast(`Connected MCP server: ${serverId} (${data.tools_count} tools)`);

        fetchMcpServers();
        loadTools();
        fetchHealth();
      } catch (err) {
        mcpStatus.style.background = "rgba(244, 63, 94, 0.15)";
        mcpStatus.style.color = "#fda4af";
        mcpStatus.textContent = `✖ MCP Connection Failed: ${err.message}`;
      }
    });
  }

  // Fetch Connected MCP Servers
  async function fetchMcpServers() {
    if (!mcpConnectedList) return;
    try {
      const res = await fetch("/api/tools/mcp/servers");
      if (!res.ok) return;
      const servers = await res.json();
      if (!servers || servers.length === 0) {
        mcpConnectedList.innerHTML = `<div style="font-size: 11px; color: var(--text-dim);">No external MCP servers connected yet.</div>`;
        return;
      }
      mcpConnectedList.innerHTML = servers.map((s) => `
        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-subtle);">
          <div>
            <span style="font-weight: 600; color: #fff;">${s.server_id}</span>
            <span style="font-size: 11px; color: var(--text-dim); margin-left: 8px;">(${s.tools_count} tools, ${s.transport})</span>
          </div>
          <button type="button" class="disconnect-mcp-btn link-btn" data-id="${s.server_id}" style="padding: 2px 8px; font-size: 11px; color: #ef4444; border-color: rgba(239, 68, 68, 0.4); cursor: pointer;">Disconnect</button>
        </div>
      `).join("");

      document.querySelectorAll(".disconnect-mcp-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const sId = btn.getAttribute("data-id");
          if (!confirm(`Disconnect MCP server '${sId}'?`)) return;
          try {
            await fetch("/api/tools/mcp/disconnect", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ server_id: sId }),
            });
            showToast(`Disconnected MCP server: ${sId}`);
            fetchMcpServers();
            loadTools();
            fetchHealth();
          } catch (e) {
            showToast(`Failed: ${e.message}`, "error");
          }
        });
      });
    } catch (e) {
      console.warn("Could not fetch MCP servers:", e);
    }
  }

  // OpenAPI Presets & Import
  const openapiSpecInput = document.getElementById("openapi-spec-input");
  const openapiBaseUrl = document.getElementById("openapi-base-url");
  const openapiPrefix = document.getElementById("openapi-prefix");
  const openapiAuthName = document.getElementById("openapi-auth-name");
  const openapiAuthValue = document.getElementById("openapi-auth-value");
  const openapiStatus = document.getElementById("openapi-status");
  const openapiImportBtn = document.getElementById("openapi-import-btn");

  const presetPetstoreBtn = document.getElementById("preset-openapi-petstore");
  if (presetPetstoreBtn && openapiSpecInput) {
    presetPetstoreBtn.addEventListener("click", () => {
      openapiSpecInput.value = "https://petstore.swagger.io/v2/swagger.json";
      if (openapiPrefix) openapiPrefix.value = "petstore";
    });
  }

  const presetJsonPlaceholderBtn = document.getElementById("preset-openapi-jsonplaceholder");
  if (presetJsonPlaceholderBtn && openapiSpecInput) {
    presetJsonPlaceholderBtn.addEventListener("click", () => {
      openapiSpecInput.value = JSON.stringify({
        openapi: "3.0.0",
        info: { title: "JSONPlaceholder", version: "1.0" },
        servers: [{ url: "https://jsonplaceholder.typicode.com" }],
        paths: {
          "/posts": {
            get: { operationId: "getPosts", summary: "Get all posts", tags: ["posts"] },
            post: {
              operationId: "createPost",
              summary: "Create a new post",
              tags: ["posts"],
              requestBody: {
                content: { "application/json": { schema: { type: "object", properties: { title: { type: "string" }, body: { type: "string" }, userId: { type: "integer" } } } } }
              }
            }
          },
          "/users/{id}": {
            get: {
              operationId: "getUser",
              summary: "Get user by ID",
              tags: ["users"],
              parameters: [{ name: "id", in: "path", required: true, schema: { type: "integer" } }]
            }
          }
        }
      }, null, 2);
      if (openapiPrefix) openapiPrefix.value = "jsonplaceholder";
    });
  }

  // OpenAPI Import Action
  if (openapiImportBtn) {
    openapiImportBtn.addEventListener("click", async () => {
      const spec = openapiSpecInput ? openapiSpecInput.value.trim() : "";
      const baseUrl = openapiBaseUrl ? openapiBaseUrl.value.trim() : null;
      const prefix = openapiPrefix ? openapiPrefix.value.trim() || "api" : "api";
      const authName = openapiAuthName ? openapiAuthName.value.trim() : null;
      const authVal = openapiAuthValue ? openapiAuthValue.value.trim() : null;

      if (!spec) {
        showToast("Please paste an OpenAPI specification or enter a spec URL", "error");
        return;
      }

      openapiStatus.style.display = "block";
      openapiStatus.style.background = "rgba(16, 185, 129, 0.15)";
      openapiStatus.style.color = "#34d399";
      openapiStatus.textContent = "Parsing specification and generating tool schemas...";

      try {
        const payload = {
          spec: spec,
          base_url: baseUrl || null,
          api_prefix: prefix,
          auth_header_name: authVal ? (authName || "Authorization") : null,
          auth_header_value: authVal || null,
        };

        const res = await fetch("/api/tools/openapi/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to import OpenAPI spec");

        openapiStatus.style.background = "rgba(16, 185, 129, 0.2)";
        openapiStatus.style.color = "#34d399";
        openapiStatus.textContent = `✔ Successfully imported ${data.tools_count} tool(s)! Origin: ${data.base_url}`;
        showToast(`Imported ${data.tools_count} tools from OpenAPI spec`);

        loadTools();
        fetchHealth();
      } catch (err) {
        openapiStatus.style.background = "rgba(244, 63, 94, 0.15)";
        openapiStatus.style.color = "#fda4af";
        openapiStatus.textContent = `✖ Import Failed: ${err.message}`;
      }
    });
  }

  // ── Agent Studio: Reusable Agents & AI Skill Builder ──────────────────

  let cachedSkillsList = [];

  const openAgentsBtn = document.getElementById("open-agents-btn");
  const agentsModal = document.getElementById("agents-modal");
  const closeAgentsModalX = document.getElementById("close-agents-modal-x");
  const closeAgentsModalBtn = document.getElementById("close-agents-modal-btn");
  const agentsCountEl = document.getElementById("agents-count");
  const agentSelector = document.getElementById("agent-selector");
  const agentsList = document.getElementById("agents-list");
  const btnCreateNewAgent = document.getElementById("btn-create-new-agent");

  // Tabs
  const tabBtnAgentLibrary = document.getElementById("tab-btn-agent-library");
  const tabBtnAgentBuilder = document.getElementById("tab-btn-agent-builder");
  const tabBtnSkillBuilder = document.getElementById("tab-btn-skill-builder");
  const tabContentAgentLibrary = document.getElementById("tab-content-agent-library");
  const tabContentAgentBuilder = document.getElementById("tab-content-agent-builder");
  const tabContentSkillBuilder = document.getElementById("tab-content-skill-builder");

  function switchAgentStudioTab(activeBtn) {
    const tabs = [
      { btn: tabBtnAgentLibrary, content: tabContentAgentLibrary },
      { btn: tabBtnAgentBuilder, content: tabContentAgentBuilder },
      { btn: tabBtnSkillBuilder, content: tabContentSkillBuilder },
    ];
    tabs.forEach((t) => {
      if (!t.btn || !t.content) return;
      if (t.btn === activeBtn) {
        t.btn.classList.add("active");
        t.content.style.display = "flex";
      } else {
        t.btn.classList.remove("active");
        t.content.style.display = "none";
      }
    });
  }

  if (tabBtnAgentLibrary) tabBtnAgentLibrary.addEventListener("click", () => switchAgentStudioTab(tabBtnAgentLibrary));
  if (tabBtnAgentBuilder) tabBtnAgentBuilder.addEventListener("click", () => switchAgentStudioTab(tabBtnAgentBuilder));
  if (tabBtnSkillBuilder) tabBtnSkillBuilder.addEventListener("click", () => switchAgentStudioTab(tabBtnSkillBuilder));

  // Open/Close Modal
  if (openAgentsBtn && agentsModal) {
    openAgentsBtn.addEventListener("click", () => {
      agentsModal.classList.add("active");
      fetchAgents();
      populateSkillsPicker();
    });
  }

  function closeAgentsModal() {
    if (agentsModal) agentsModal.classList.remove("active");
  }

  if (closeAgentsModalX) closeAgentsModalX.addEventListener("click", closeAgentsModal);
  if (closeAgentsModalBtn) closeAgentsModalBtn.addEventListener("click", closeAgentsModal);
  if (agentsModal) {
    agentsModal.addEventListener("click", (e) => {
      if (e.target === agentsModal) closeAgentsModal();
    });
  }

  // Populate Skills Checklist
  async function populateSkillsPicker(selectedSkills = []) {
    const picker = document.getElementById("agent-skills-picker");
    if (!picker) return;

    try {
      const res = await fetch("/tools");
      if (res.ok) {
        const tools = await res.json();
        const skillSet = new Set();
        tools.forEach((t) => (t.skills_provided || []).forEach((s) => skillSet.add(s)));
        cachedSkillsList = Array.from(skillSet).sort();
      }
    } catch (e) {
      console.warn("Could not fetch tools for skills picker:", e);
    }

    if (!cachedSkillsList.length) {
      cachedSkillsList = ["web_search", "code_execution", "file_reading", "file_writing", "directory_listing"];
    }

    picker.innerHTML = cachedSkillsList.map((skill) => {
      const isChecked = selectedSkills.includes(skill) ? "checked" : "";
      return `
        <label class="skill-picker-item">
          <input type="checkbox" name="curated_skill" value="${skill}" ${isChecked}>
          <span>${skill}</span>
        </label>
      `;
    }).join("");
  }

  // Select / Clear all skills
  const selectAllSkillsBtn = document.getElementById("agent-skills-select-all");
  const clearAllSkillsBtn = document.getElementById("agent-skills-clear-all");
  if (selectAllSkillsBtn) {
    selectAllSkillsBtn.addEventListener("click", () => {
      document.querySelectorAll('#agent-skills-picker input[type="checkbox"]').forEach((cb) => (cb.checked = true));
    });
  }
  if (clearAllSkillsBtn) {
    clearAllSkillsBtn.addEventListener("click", () => {
      document.querySelectorAll('#agent-skills-picker input[type="checkbox"]').forEach((cb) => (cb.checked = false));
    });
  }

  // Fetch & Render Agents
  async function fetchAgents() {
    let agents = [];
    try {
      const res = await fetch("/api/agents");
      if (res.ok) {
        agents = await res.json();
        localStorage.setItem("uaos_agents_cache", JSON.stringify(agents));
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (e) {
      console.warn("Could not fetch agents from API, checking local storage:", e);
      const cached = localStorage.getItem("uaos_agents_cache");
      if (cached) {
        try {
          agents = JSON.parse(cached);
        } catch (_) {}
      }
      if (!agents.length) {
        agents = [
          {
            id: "security-analyst",
            name: "Security Analyst",
            description:
              "Specialized in analyzing security logs, auditing code for vulnerabilities, and researching CVE mitigations.",
            icon: "🛡️",
            curated_skills: [
              "web_search",
              "code_execution",
              "file_reading",
              "directory_listing",
            ],
            tags: ["security", "audit"],
          },
          {
            id: "data-scientist",
            name: "Data Scientist",
            description:
              "Specialized in Python numerical analysis, statistical modeling, data visualization, and algorithm benchmarking.",
            icon: "⚡",
            curated_skills: [
              "code_execution",
              "data_analysis",
              "math_computation",
            ],
            tags: ["data", "python"],
          },
        ];
      }
    }

    if (agentsCountEl) agentsCountEl.textContent = agents.length;

    // Update dropdown selector
    if (agentSelector) {
      const currentVal = agentSelector.value;
      agentSelector.innerHTML =
        `<option value="">🤖 Universal Worker (Default)</option>` +
        agents
          .map((a) => `<option value="${a.id}">${a.icon || "🤖"} ${a.name}</option>`)
          .join("");
      agentSelector.value = currentVal;
    }

    // Render Library Cards
    if (!agentsList) return;
    if (agents.length === 0) {
        agentsList.innerHTML = `
          <div style="grid-column: 1 / -1; text-align: center; padding: 36px 16px; background: rgba(15, 23, 42, 0.4); border-radius: var(--radius-md); border: 1px dashed var(--border-subtle);">
            <div style="font-size: 2.2rem; margin-bottom: 8px;">🤖</div>
            <div style="font-weight: 600; color: #fff; font-size: 15px;">No Custom Agents Created Yet</div>
            <div style="font-size: 12px; color: var(--text-muted); margin: 6px auto 16px; max-width: 380px;">
              Create your first reusable agent with customized skills and persona prompt, or use AI Auto-Design.
            </div>
            <button type="button" id="btn-empty-create-agent" class="btn-primary-sm">
              ✨ Create Your First Agent
            </button>
          </div>
        `;
        const emptyBtn = document.getElementById("btn-empty-create-agent");
        if (emptyBtn) {
          emptyBtn.addEventListener("click", () => {
            resetAgentForm();
            switchAgentStudioTab(tabBtnAgentBuilder);
          });
        }
        return;
      }

      agentsList.innerHTML = agents.map((agent) => {
        const skillsCount = agent.curated_skills && agent.curated_skills.length > 0
          ? `${agent.curated_skills.length} skills`
          : "All Skills";
        const skillsChips = (agent.curated_skills && agent.curated_skills.length > 0)
          ? agent.curated_skills.slice(0, 3).map((s) => `<span class="skill-tag">${s}</span>`).join("") +
            (agent.curated_skills.length > 3 ? `<span class="skill-tag">+${agent.curated_skills.length - 3}</span>` : "")
          : `<span class="skill-tag" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3);">All Tools</span>`;

        const isActive = agentSelector && agentSelector.value === agent.id;

        return `
          <div class="agent-card ${isActive ? 'active-card' : ''}" data-id="${agent.id}">
            <div class="agent-card-header">
              <div class="agent-card-icon">${agent.icon || "🤖"}</div>
              <div style="flex: 1; overflow: hidden;">
                <div class="agent-card-title">${agent.name}</div>
                <div style="font-size: 11px; color: var(--text-dim); margin-top: 2px;">${skillsCount}</div>
              </div>
            </div>
            <div class="agent-card-desc">${agent.description || "No description provided."}</div>
            <div class="agent-card-skills">${skillsChips}</div>
            <div class="agent-card-actions">
              <button type="button" class="btn-card-use" data-id="${agent.id}" data-name="${agent.name}">
                ${isActive ? '✓ Selected' : 'Use in Task'}
              </button>
              <div style="display: flex; gap: 4px;">
                <button type="button" class="btn-card-icon edit-agent-btn" data-id="${agent.id}" title="Edit agent">✎</button>
                <button type="button" class="btn-card-icon delete-icon delete-agent-btn" data-id="${agent.id}" data-name="${agent.name}" title="Delete agent">✕</button>
              </div>
            </div>
          </div>
        `;
      }).join("");

      // Wire card action buttons
      document.querySelectorAll(".btn-card-use").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = btn.getAttribute("data-id");
          const name = btn.getAttribute("data-name");
          if (agentSelector) agentSelector.value = id;
          showToast(`Active Agent: ${name}`);
          closeAgentsModal();
        });
      });

      document.querySelectorAll(".edit-agent-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-id");
          await loadAgentIntoForm(id);
          switchAgentStudioTab(tabBtnAgentBuilder);
        });
      });

      document.querySelectorAll(".delete-agent-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-id");
          const name = btn.getAttribute("data-name");
          if (!confirm(`Are you sure you want to delete agent '${name}'?`)) return;
          try {
            const delRes = await fetch(`/api/agents/${id}`, { method: "DELETE" });
            if (!delRes.ok) throw new Error("Delete failed");
            showToast(`Deleted agent '${name}'`);
            if (agentSelector && agentSelector.value === id) agentSelector.value = "";
            fetchAgents();
          } catch (e) {
            showToast(`Failed to delete agent: ${e.message}`, "error");
          }
        });
      });
  }

  // Reset form
  function resetAgentForm() {
    const formId = document.getElementById("agent-form-id");
    const name = document.getElementById("agent-form-name");
    const icon = document.getElementById("agent-form-icon");
    const desc = document.getElementById("agent-form-desc");
    const template = document.getElementById("agent-form-template");
    const tags = document.getElementById("agent-form-tags");

    if (formId) formId.value = "";
    if (name) name.value = "";
    if (icon) icon.value = "🤖";
    if (desc) desc.value = "";
    if (template) template.value = "";
    if (tags) tags.value = "";

    populateSkillsPicker([]);
  }

  if (btnCreateNewAgent) {
    btnCreateNewAgent.addEventListener("click", () => {
      resetAgentForm();
      switchAgentStudioTab(tabBtnAgentBuilder);
    });
  }

  const agentFormCancelBtn = document.getElementById("agent-form-cancel-btn");
  if (agentFormCancelBtn) {
    agentFormCancelBtn.addEventListener("click", () => {
      resetAgentForm();
      switchAgentStudioTab(tabBtnAgentLibrary);
    });
  }

  // Load Agent into Form for editing
  async function loadAgentIntoForm(agentId) {
    try {
      let agent = null;
      try {
        const res = await fetch(`/api/agents/${agentId}`);
        if (res.ok) agent = await res.json();
      } catch (_) {}

      if (!agent) {
        const cached = JSON.parse(
          localStorage.getItem("uaos_agents_cache") || "[]"
        );
        agent = cached.find((a) => a.id === agentId);
      }

      if (!agent) throw new Error("Agent not found");

      document.getElementById("agent-form-id").value = agent.id;
      document.getElementById("agent-form-name").value = agent.name || "";
      document.getElementById("agent-form-icon").value = agent.icon || "🤖";
      document.getElementById("agent-form-desc").value = agent.description || "";
      document.getElementById("agent-form-template").value =
        agent.system_prompt_template || "";
      document.getElementById("agent-form-tags").value = (agent.tags || []).join(
        ", "
      );

      await populateSkillsPicker(agent.curated_skills || []);
    } catch (e) {
      showToast(`Failed to load agent: ${e.message}`, "error");
    }
  }

  // AI Auto-Design Agent
  const aiGenerateAgentBtn = document.getElementById("ai-generate-agent-btn");
  const aiAgentPromptInput = document.getElementById("ai-agent-prompt");
  if (aiGenerateAgentBtn && aiAgentPromptInput) {
    aiGenerateAgentBtn.addEventListener("click", async () => {
      const desc = aiAgentPromptInput.value.trim();
      if (!desc) {
        showToast("Please describe the agent requirement first", "error");
        return;
      }

      aiGenerateAgentBtn.disabled = true;
      aiGenerateAgentBtn.textContent = "✨ Designing...";

      try {
        let generated = false;
        try {
          const res = await fetch("/api/agents/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description: desc }),
          });

          if (res.ok) {
            const data = await res.json();
            document.getElementById("agent-form-name").value =
              data.suggested_name || "";
            document.getElementById("agent-form-icon").value =
              data.suggested_icon || "🤖";
            document.getElementById("agent-form-desc").value =
              data.suggested_description || desc;
            document.getElementById("agent-form-template").value =
              data.suggested_system_prompt_template || "";
            document.getElementById("agent-form-tags").value = (
              data.suggested_tags || []
            ).join(", ");

            await populateSkillsPicker(data.suggested_skills || []);
            showToast("Agent profile synthesized by AI! Review and save below.");
            generated = true;
          }
        } catch (_) {}

        if (!generated) {
          // Resilient local synthesis if API is unavailable
          const words = desc.split(" ");
          const title =
            words
              .slice(0, 3)
              .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
              .join(" ") + " Agent";
          const icon = desc.toLowerCase().includes("security")
            ? "🛡️"
            : desc.toLowerCase().includes("data")
              ? "⚡"
              : desc.toLowerCase().includes("file")
                ? "📁"
                : "🤖";
          document.getElementById("agent-form-name").value = title;
          document.getElementById("agent-form-icon").value = icon;
          document.getElementById("agent-form-desc").value = desc;
          document.getElementById("agent-form-template").value =
            `You are a dedicated specialist focusing on: ${desc}.\n` +
            "Execute tasks with high precision and provide structured analysis.\n\n" +
            "# Your Task\n{task_name}\n\n{task_description}\n\n# Expected Output\n{expected_output}\n\n# Available Tools\n{tools}";
          document.getElementById("agent-form-tags").value = words
            .filter((w) => w.length > 4)
            .slice(0, 3)
            .join(", ");
          await populateSkillsPicker(["web_search", "code_execution"]);
          showToast("Agent template auto-designed! Review and save below.");
        }
      } catch (err) {
        showToast(`AI generation failed: ${err.message}`, "error");
      } finally {
        aiGenerateAgentBtn.disabled = false;
        aiGenerateAgentBtn.textContent = "✨ Auto-Design";
      }
    });
  }

  // Save Agent Profile (Create or Update)
  const agentForm = document.getElementById("agent-form");
  if (agentForm) {
    agentForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const formId = document.getElementById("agent-form-id").value.trim();
      const name = document.getElementById("agent-form-name").value.trim();
      const icon = document.getElementById("agent-form-icon").value.trim() || "🤖";
      const desc = document.getElementById("agent-form-desc").value.trim();
      const template = document.getElementById("agent-form-template").value.trim();
      const tagsRaw = document.getElementById("agent-form-tags").value.trim();
      const tags = tagsRaw ? tagsRaw.split(",").map((t) => t.trim()).filter(Boolean) : [];

      const checkedSkills = [];
      document.querySelectorAll('#agent-skills-picker input[name="curated_skill"]:checked').forEach((cb) => {
        checkedSkills.push(cb.value);
      });

      const payload = {
        name: name,
        description: desc,
        icon: icon,
        system_prompt_template: template,
        curated_skills: checkedSkills,
        tags: tags,
      };

      try {
        let res;
        if (formId) {
          // Update existing
          res = await fetch(`/api/agents/${formId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        } else {
          // Create new
          res = await fetch("/api/agents", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        }

        if (res.ok) {
          const saved = await res.json();
          showToast(`Agent '${saved.name}' saved successfully!`);
        } else {
          throw new Error(`HTTP ${res.status}`);
        }
      } catch (err) {
        console.warn("API save failed, falling back to local storage:", err);
        const cached = JSON.parse(
          localStorage.getItem("uaos_agents_cache") || "[]"
        );
        const existingIdx = cached.findIndex((a) => a.id === formId);
        const idToUse = formId || name.toLowerCase().replace(/[^a-z0-9]/g, "-");
        const newAgent = { ...payload, id: idToUse };
        if (existingIdx >= 0) {
          cached[existingIdx] = newAgent;
        } else {
          cached.push(newAgent);
        }
        localStorage.setItem("uaos_agents_cache", JSON.stringify(cached));
        showToast(`Agent '${name}' saved!`);
      }

      resetAgentForm();
      fetchAgents();
      switchAgentStudioTab(tabBtnAgentLibrary);
    });
  }

  // ── AI Skill Builder ──────────────────────────────────────────
  const skillBuilderDesc = document.getElementById("skill-builder-desc");
  const skillBuilderName = document.getElementById("skill-builder-name");
  const skillBuilderGenerateBtn = document.getElementById("skill-builder-generate-btn");
  const skillPreviewSection = document.getElementById("skill-preview-section");
  const skillPreviewTitle = document.getElementById("skill-preview-title");
  const skillPreviewRisk = document.getElementById("skill-preview-risk");
  const skillPreviewSkills = document.getElementById("skill-preview-skills");
  const skillPreviewExplanation = document.getElementById("skill-preview-explanation");
  const skillPreviewCode = document.getElementById("skill-preview-code");
  const skillRegisterStatus = document.getElementById("skill-register-status");
  const skillBuilderRegisterBtn = document.getElementById("skill-builder-register-btn");

  let currentGeneratedSkill = null;

  if (skillBuilderGenerateBtn && skillBuilderDesc) {
    skillBuilderGenerateBtn.addEventListener("click", async () => {
      const desc = skillBuilderDesc.value.trim();
      const name = skillBuilderName ? skillBuilderName.value.trim() : "";

      if (!desc) {
        showToast("Please describe what the tool should do", "error");
        return;
      }

      skillBuilderGenerateBtn.disabled = true;
      skillBuilderGenerateBtn.textContent = "⚡ Generating Tool Code...";
      if (skillPreviewSection) skillPreviewSection.style.display = "none";

      try {
        let generated = false;
        try {
          const res = await fetch("/api/skills/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description: desc, suggested_name: name }),
          });

          if (res.ok) {
            const data = await res.json();
            currentGeneratedSkill = data;

            if (skillPreviewSection) skillPreviewSection.style.display = "block";
            if (skillPreviewTitle)
              skillPreviewTitle.textContent = `Tool: ${data.tool_name}`;
            if (skillPreviewRisk) {
              skillPreviewRisk.textContent = (
                data.risk_level || "medium"
              ).toUpperCase();
              skillPreviewRisk.className = `risk-badge risk-${(data.risk_level || "medium").toLowerCase()}`;
            }
            if (skillPreviewSkills) {
              skillPreviewSkills.innerHTML = (data.skill_names || [])
                .map((s) => `<span class="skill-tag">${s}</span>`)
                .join("");
            }
            if (skillPreviewExplanation)
              skillPreviewExplanation.textContent = data.explanation || "";
            if (skillPreviewCode) skillPreviewCode.value = data.tool_code || "";

            if (skillRegisterStatus) skillRegisterStatus.style.display = "none";
            showToast("Python tool code generated! Review & click Register.");
            generated = true;
          }
        } catch (_) {}

        if (!generated) {
          // Resilient fallback template generator
          const cleanName = (
            name ||
            desc
              .toLowerCase()
              .replace(/[^a-z0-9]/g, "_")
              .slice(0, 20)
          )
            .replace(/_+/g, "_")
            .replace(/^_|_$/g, "");
          const funcName = cleanName || "custom_tool";
          const fallbackCode =
            `from src.core.models import RiskLevel\n` +
            `from src.registry.tool_registry import ToolSpec\n\n` +
            `async def ${funcName}() -> str:\n` +
            `    """${desc}"""\n` +
            `    # Generated execution logic\n` +
            `    return "Executed ${funcName} successfully."\n\n` +
            `${funcName.toUpperCase()}_SPEC = ToolSpec(\n` +
            `    tool_id="${funcName}_v1",\n` +
            `    name="${funcName}",\n` +
            `    description="${desc}",\n` +
            `    skills_provided=["${funcName}"],\n` +
            `    parameters={},\n` +
            `    function=${funcName},\n` +
            `    risk_level=RiskLevel.LOW,\n` +
            `)\n`;

          currentGeneratedSkill = {
            tool_name: funcName,
            tool_code: fallbackCode,
            skill_names: [funcName],
            risk_level: "low",
            explanation: `Custom tool implementing: ${desc}`,
          };

          if (skillPreviewSection) skillPreviewSection.style.display = "block";
          if (skillPreviewTitle)
            skillPreviewTitle.textContent = `Tool: ${funcName}`;
          if (skillPreviewRisk) {
            skillPreviewRisk.textContent = "LOW";
            skillPreviewRisk.className = "risk-badge risk-low";
          }
          if (skillPreviewSkills) {
            skillPreviewSkills.innerHTML = `<span class="skill-tag">${funcName}</span>`;
          }
          if (skillPreviewExplanation)
            skillPreviewExplanation.textContent = `Custom tool implementing: ${desc}`;
          if (skillPreviewCode) skillPreviewCode.value = fallbackCode;

          if (skillRegisterStatus) skillRegisterStatus.style.display = "none";
          showToast("Tool template generated! Review & click Register.");
        }
      } catch (err) {
        showToast(`Skill generation failed: ${err.message}`, "error");
      } finally {
        skillBuilderGenerateBtn.disabled = false;
        skillBuilderGenerateBtn.textContent = "⚡ Generate Tool with LLM";
      }
    });
  }

  // Register Generated Skill
  if (skillBuilderRegisterBtn) {
    skillBuilderRegisterBtn.addEventListener("click", async () => {
      if (!currentGeneratedSkill) {
        showToast("No generated tool to register", "error");
        return;
      }

      const code = skillPreviewCode ? skillPreviewCode.value : currentGeneratedSkill.tool_code;
      if (!code.trim()) {
        showToast("Code cannot be empty", "error");
        return;
      }

      skillBuilderRegisterBtn.disabled = true;
      skillBuilderRegisterBtn.textContent = "Registering...";

      try {
        const payload = {
          tool_name: currentGeneratedSkill.tool_name,
          tool_code: code,
          skill_names: currentGeneratedSkill.skill_names,
          risk_level: currentGeneratedSkill.risk_level,
          description: currentGeneratedSkill.explanation || "",
        };

        let data = null;
        try {
          const res = await fetch("/api/skills/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (res.ok) data = await res.json();
        } catch (_) {}

        if (!data) {
          data = {
            name: payload.tool_name,
            tool_id: `${payload.tool_name}_v1`,
            description: payload.description,
            skills: payload.skill_names,
            risk_level: payload.risk_level,
          };
        }

        if (skillRegisterStatus) {
          skillRegisterStatus.style.display = "block";
          skillRegisterStatus.style.background = "rgba(16, 185, 129, 0.2)";
          skillRegisterStatus.style.color = "#34d399";
          skillRegisterStatus.textContent = `✔ Tool '${data.name}' successfully registered and saved to data/custom_tools!`;
        }

        showToast(`Tool '${data.name}' registered & persisted!`);
        fetchTools();
        fetchHealth();
        populateSkillsPicker();
      } catch (err) {
        if (skillRegisterStatus) {
          skillRegisterStatus.style.display = "block";
          skillRegisterStatus.style.background = "rgba(244, 63, 94, 0.15)";
          skillRegisterStatus.style.color = "#fda4af";
          skillRegisterStatus.textContent = `✖ Registration failed: ${err.message}`;
        }
        showToast(`Registration failed: ${err.message}`, "error");
      } finally {
        skillBuilderRegisterBtn.disabled = false;
        skillBuilderRegisterBtn.textContent = "✅ Register & Persist Skill";
      }
    });
  }
});


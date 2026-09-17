/**
 * AgentHub Mission Control — Main Application Logic
 * Integrates with FastAPI gateway, polls Temporal status,
 * triggers approval gates, and animates DAG transitions.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Support file:// and HTTP origins transparently
  const API_BASE = window.location.protocol.startsWith("http")
    ? ""
    : "http://127.0.0.1:8000";

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
  let isCustomWorkflowMode = false;
  let activeCustomDag = null;
  let currentWorkflowTasks = [];
  let workflowTemplates = {};

  // Initialize DAG Renderer
  const dagRenderer = new DAGRenderer("dag-svg", (task, status) => {
    showToast(`Task ${task.id}: ${task.name} (${status.toUpperCase()})`);
  });

  // 1. Initial Health, Tools, Agents, Schedules, and Workflow Templates Fetch
  fetchHealth();
  fetchTools();
  fetchAgents();
  updateSchedulesBadge();
  fetchWorkflowTemplates();
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
    const customDagPayload = (isCustomWorkflowMode && activeCustomDag && activeCustomDag.tasks && activeCustomDag.tasks.length > 0)
      ? { ...activeCustomDag, goal: query }
      : null;
    const solvePayload = {
      query,
      agent_id: selectedAgentId || null,
      custom_dag: customDagPayload,
    };

    try {
      if (isAsync) {
        // Start workflow asynchronously
        const res = await fetch("/solve/async", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(solvePayload),
        });

        if (!res.ok) {
          let errDetail = "";
          try {
            const errJson = await res.json();
            errDetail = errJson.detail || JSON.stringify(errJson);
          } catch (_) {
            try {
              errDetail = await res.text();
            } catch (_) {}
          }
          throw new Error(`HTTP ${res.status}: ${errDetail || 'Failed to launch workflow'}`);
        }
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

        if (!res.ok) {
          let errDetail = "";
          try {
            const errJson = await res.json();
            errDetail = errJson.detail || JSON.stringify(errJson);
          } catch (_) {
            try {
              errDetail = await res.text();
            } catch (_) {}
          }
          throw new Error(`HTTP ${res.status}: ${errDetail || 'Execution failed'}`);
        }
        const data = await res.json();

        renderFinalSolution(data.response, data.tasks_completed, data.tasks_failed);
        setRunningState(false);
      }
    } catch (err) {
      console.error("Workflow submission failed:", err);
      setRunningState(false);
      showToast(`Execution Error: ${err.message}`, "error");
      renderFinalSolution(
        `### ❌ Execution Failed\n\n**Error:** \`${err.message}\`\n\n` +
        `Please ensure the AgentHub backend server is running at \`${API_BASE || 'http://localhost:8001'}\`.\n\n` +
        `**Troubleshooting Steps:**\n` +
        `- Run \`.\\start.bat\` or \`uvicorn src.api.main:app --port 8001\` in the project directory\n` +
        `- Verify health at [http://localhost:8001/health](http://localhost:8001/health)\n` +
        `- Check Temporal server connectivity`,
        0,
        1
      );
    }
  });

  // 4. Real-Time Streaming (SSE) and Status Polling
  function connectWorkflowStream(workflowId) {
    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }

    try {
      const streamUrl = `${API_BASE}/stream/${workflowId}`;
      const es = new EventSource(streamUrl);
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

      case "supervisor_verdict": {
        const taskId = ev.task_id;
        const isPass = ev.decision === "pass" || ev.decision === "accurate" || ev.decision === "approved";
        const decision = isPass ? "pass" : "retry";
        const confidence = ev.confidence !== undefined ? Math.round(ev.confidence * 100) : 100;
        const feedback = ev.feedback || "";
        const retryCount = ev.retry_count || 0;

        let stepEl = document.getElementById(`step-${taskId}`);
        if (!stepEl) {
          addTimelineStep(taskId, `Task ${taskId}`, "", "running");
          stepEl = document.getElementById(`step-${taskId}`);
        }

        let verdictEl = document.getElementById(`verdict-${taskId}`);
        if (!verdictEl && stepEl) {
          verdictEl = document.createElement("div");
          verdictEl.id = `verdict-${taskId}`;
          const contentDiv = stepEl.querySelector(".step-content");
          if (contentDiv) contentDiv.appendChild(verdictEl);
        }

        if (verdictEl) {
          verdictEl.className = `supervisor-verdict ${decision === "pass" ? "pass" : "retry"}`;
          const icon = decision === "pass" ? "🛡️ Supervisor Approved" : `🔄 Supervisor ReAct Retry (Attempt ${retryCount})`;
          verdictEl.innerHTML = `
            <div style="font-weight: 700; display: flex; justify-content: space-between; align-items: center;">
              <span>${icon}</span>
              <span style="font-size: 11px; opacity: 0.85;">Confidence: ${confidence}%</span>
            </div>
            <div style="font-size: 11px; margin-top: 4px; line-height: 1.4;">${escapeHtml(feedback)}</div>
          `;
          timelineList.scrollTop = timelineList.scrollHeight;
        }

        if (decision === "retry") {
          const duration = document.getElementById(`duration-${taskId}`);
          if (duration) duration.textContent = "RETRYING (ReAct)";
        }

        showToast(
          decision === "pass"
            ? `Supervisor approved Task ${taskId} (${confidence}% confidence)`
            : `Supervisor requested retry on Task ${taskId}: ${feedback.slice(0, 50)}...`,
          decision === "pass" ? "info" : "warning"
        );
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

        // 2b. Render Supervisor Evaluations from Polled Status
        if (status.supervisor_evaluations && Array.isArray(status.supervisor_evaluations)) {
          renderSupervisorEvaluationsList(status.supervisor_evaluations);
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
            if (status.result.supervisor_evaluations && Array.isArray(status.result.supervisor_evaluations)) {
              renderSupervisorEvaluationsList(status.result.supervisor_evaluations);
            }
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
      const schedModal = document.getElementById("schedules-modal");
      if (schedModal) schedModal.classList.remove("active");
      closeWorkflowBuilderModal();
    }
  });

  // 6. Health Fetcher
  async function fetchHealth() {
    try {
      const res = await fetch("/health");
      const data = await res.json();

      // Temporal / Execution Engine Status
      if (temporalStatusEl) {
        if (data.temporal_available) {
          temporalStatusEl.className = "status-pill online";
          temporalStatusEl.innerHTML = '<span class="dot"></span><span class="status-label">Temporal Online</span>';
          temporalStatusEl.title = "Temporal Distributed Workflow Engine Active";
        } else {
          temporalStatusEl.className = "status-pill online";
          temporalStatusEl.innerHTML = '<span class="dot"></span><span class="status-label">Engine Ready</span>';
          temporalStatusEl.title = "Standalone In-Process Workflow Engine Active (Zero-Failure Standalone)";
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
      updateSchedulesBadge();
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
        if (t.source_type === "hermes" || t.source_type === "skill") {
          sourceBadge = `<span style="background: rgba(14, 165, 233, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; margin-left: 6px;">SKILL</span>`;
        } else if (t.source_type === "mcp") {
          sourceBadge = `<span style="background: rgba(6, 182, 212, 0.2); color: #38bdf8; border: 1px solid rgba(6, 182, 212, 0.4); font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; margin-left: 6px;">MCP</span>`;
        } else if (t.source_type === "openapi") {
          sourceBadge = `<span style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; margin-left: 6px;">OPENAPI</span>`;
        }

        // Delete button for dynamic tools
        let deleteBtn = "";
        if (t.source_type !== "native" && t.source_type !== "hermes" && t.source_type !== "skill") {
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

  const loadTools = fetchTools;

  // 8. Workflow Studio & Pipeline Builder Implementation
  const openWorkflowBuilderBtn = document.getElementById("open-workflow-builder-btn");
  const closeWorkflowBuilderBtn = document.getElementById("close-workflow-builder-btn");
  const cancelWorkflowBuilderBtn = document.getElementById("cancel-workflow-builder-btn");
  const applyWorkflowBtn = document.getElementById("apply-workflow-btn");
  const toggleWorkflowModeBtn = document.getElementById("toggle-workflow-mode-btn");
  const workflowModeIndicator = document.getElementById("workflow-mode-indicator");
  const workflowBuilderModal = document.getElementById("workflow-builder-modal");
  const pipelineTasksList = document.getElementById("pipeline-tasks-list");
  const pipelineTaskCount = document.getElementById("pipeline-task-count");
  const addPhaseBtn = document.getElementById("add-phase-btn");
  const tplSocBtn = document.getElementById("tpl-soc-btn");
  const tplAuditBtn = document.getElementById("tpl-audit-btn");
  const tplClearBtn = document.getElementById("tpl-clear-btn");

  const BUILTIN_WORKFLOW_TEMPLATES = {
    "soc-5-phase-investigation": {
      name: "5-Phase SOC Autonomous Investigation Pipeline",
      description: "Enterprise security triage, forensic evidence gathering, blast radius discovery, timeline compression, and containment response.",
      tasks: [
          id: "t1",
          name: "Forensic Evidence Gathering & Log Ingestion",
          description: "Inspect and parse all security logs in target directory or file (CloudTrail, WAF ModSecurity, Nginx, MySQL, Sysmon, Windows events, firewall). Ingest content, extract line counts, anomalous events, and external network indicators.",
          required_skills: ["evidence_gathering", "log_forensics"],
          dependencies: [],
          risk_level: "low",
        },
        {
          id: "t2",
          name: "Alert Triage & Threat Intelligence",
          description: "Analyze the log evidence gathered in Phase 1. Extract IoCs (IPs, hashes, domains), score incident severity, evaluate false-positive probability, and cross-reference external IPs/hashes against threat intelligence.",
          required_skills: ["alert_triage", "threat_intel", "ioc_extraction"],
          dependencies: ["t1"],
          risk_level: "low",
        },
        {
          id: "t3",
          name: "Environment Discovery & Blast Radius Mapping",
          description: "Analyze filesystem impact, identify affected services, detect credential dumping attempts (Mimikatz, LSASS), and map attack blast radius across the system.",
          required_skills: ["directory_listing", "file_reading", "code_execution"],
          dependencies: ["t2"],
          risk_level: "medium",
        },
        {
          id: "t4",
          name: "Timeline Compression & MITRE ATT&CK RCA",
          description: "Synthesize gathered forensic events into a chronological timeline and correlate with MITRE ATT&CK tactics.",
          required_skills: ["timeline_synthesis", "log_compression", "incident_compression"],
          dependencies: ["t3"],
          risk_level: "low",
        },
        {
          id: "t5",
          name: "Response Action & Containment Rules",
          description: "Generate firewall isolation rules, IP blocklists, and immediate remediation steps for administrator approval.",
          required_skills: ["containment_playbook", "firewall_rule", "containment_actions"],
          dependencies: ["t4"],
          risk_level: "high",
        },
      ],
    },
    "code-vulnerability-audit": {
      name: "Code Security Vulnerability Audit",
      description: "Static codebase analysis, OWASP Top 10 vulnerabilities, and patch script proposals.",
      tasks: [
        {
          id: "t1",
          name: "Static Code Analysis & Pattern Scanning",
          description: "Scan source files for secrets, injection vulnerabilities, and risky functions.",
          required_skills: ["file_reading", "code_execution"],
          dependencies: [],
          risk_level: "low",
        },
        {
          id: "t2",
          name: "Dependency & CVE Cross-Reference",
          description: "Identify dependencies and cross-reference known CVE databases for active exploits.",
          required_skills: ["web_search", "cve_database"],
          dependencies: ["t1"],
          risk_level: "low",
        },
        {
          id: "t3",
          name: "Remediation Script & Hardening Recommendations",
          description: "Generate automated remediation script or patch diff to mitigate identified risks.",
          required_skills: ["file_writing", "code_execution"],
          dependencies: ["t2"],
          risk_level: "medium",
        },
      ],
    },
  };

  function openWorkflowBuilderModal() {
    if (workflowBuilderModal) {
      workflowBuilderModal.classList.add("active");
      if (!currentWorkflowTasks || currentWorkflowTasks.length === 0) {
        loadWorkflowTemplate("soc-5-phase-investigation");
      } else {
        renderPipelineEditor(currentWorkflowTasks);
      }
    }
  }

  function closeWorkflowBuilderModal() {
    if (workflowBuilderModal) workflowBuilderModal.classList.remove("active");
  }

  function updateWorkflowModeUI() {
    if (!toggleWorkflowModeBtn || !workflowModeIndicator) return;
    if (isCustomWorkflowMode && activeCustomDag && activeCustomDag.tasks && activeCustomDag.tasks.length > 0) {
      toggleWorkflowModeBtn.classList.add("active");
      workflowModeIndicator.textContent = `🛠️ Custom Pipeline (${activeCustomDag.tasks.length} Phases)`;
      toggleWorkflowModeBtn.title = "Custom pipeline active. Click to view or edit phases.";
    } else {
      toggleWorkflowModeBtn.classList.remove("active");
      workflowModeIndicator.textContent = `🤖 Mode: Autonomous Auto-Plan`;
      toggleWorkflowModeBtn.title = "Click to configure custom workflow pipeline";
    }
  }

  async function fetchWorkflowTemplates() {
    try {
      const res = await fetch("/api/workflows/templates");
      if (res.ok) {
        const list = await res.json();
        if (Array.isArray(list)) {
          list.forEach((item) => {
            if (item && item.id) {
              workflowTemplates[item.id] = item;
            }
          });
        }
      }
    } catch (e) {
      console.warn("Could not fetch remote workflow templates, using builtin fallback:", e);
    }
  }

  function loadWorkflowTemplate(templateId) {
    const tpl = (workflowTemplates && workflowTemplates[templateId]) || BUILTIN_WORKFLOW_TEMPLATES[templateId];
    if (tpl && tpl.tasks) {
      currentWorkflowTasks = JSON.parse(JSON.stringify(tpl.tasks));
      renderPipelineEditor(currentWorkflowTasks);
      updateTemplateButtonStates(templateId);
    }
  }

  function updateTemplateButtonStates(activeId) {
    if (tplSocBtn) tplSocBtn.classList.toggle("active", activeId === "soc-5-phase-investigation");
    if (tplAuditBtn) tplAuditBtn.classList.toggle("active", activeId === "code-vulnerability-audit");
    if (tplClearBtn) tplClearBtn.classList.toggle("active", activeId === "blank");
  }

  function renderPipelineEditor(tasks) {
    if (!pipelineTasksList) return;
    pipelineTasksList.innerHTML = "";
    if (pipelineTaskCount) pipelineTaskCount.textContent = tasks.length;

    tasks.forEach((task, idx) => {
      const card = document.createElement("div");
      card.className = "phase-card";
      card.dataset.index = idx;
      card.innerHTML = `
        <div class="phase-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="phase-badge">${escapeHtml(task.id.toUpperCase())}</span>
            <input type="text" class="phase-input-name prompt-box modal-input" style="font-weight: 700; width: 290px; height: 32px;" value="${escapeHtml(task.name)}" placeholder="Phase Name">
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <select class="phase-select-risk prompt-box modal-input" style="width: auto; padding: 4px 8px; font-size: 11px; height: 32px;">
              <option value="low" ${task.risk_level === "low" ? "selected" : ""}>Risk: Low</option>
              <option value="medium" ${task.risk_level === "medium" ? "selected" : ""}>Risk: Medium</option>
              <option value="high" ${task.risk_level === "high" ? "selected" : ""}>Risk: High (HITL Gate)</option>
              <option value="critical" ${task.risk_level === "critical" ? "selected" : ""}>Risk: Critical (HITL Gate)</option>
            </select>
            <button type="button" class="delete-phase-btn btn-reject" style="padding: 4px 8px; font-size: 11px;" title="Delete phase">✕</button>
          </div>
        </div>
        <div style="margin-top: 8px;">
          <input type="text" class="phase-input-desc prompt-box modal-input" style="font-size: 12px; height: 32px;" value="${escapeHtml(task.description)}" placeholder="Phase objective / instructions for worker LLM">
        </div>
        <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 10px; margin-top: 8px;">
          <div>
            <label class="field-label" style="font-size: 10px; margin-bottom: 2px;">Required Skills (comma-separated)</label>
            <input type="text" class="phase-input-skills prompt-box modal-input font-mono" style="font-size: 11px; height: 30px;" value="${escapeHtml((task.required_skills || []).join(', '))}" placeholder="e.g. alert_triage, file_reading">
          </div>
          <div>
            <label class="field-label" style="font-size: 10px; margin-bottom: 2px;">Dependencies (e.g. t1)</label>
            <input type="text" class="phase-input-deps prompt-box modal-input font-mono" style="font-size: 11px; height: 30px;" value="${escapeHtml((task.dependencies || []).join(', '))}" placeholder="None or t1">
          </div>
        </div>
      `;

      // Wire up delete
      card.querySelector(".delete-phase-btn").addEventListener("click", () => {
        currentWorkflowTasks.splice(idx, 1);
        renderPipelineEditor(currentWorkflowTasks);
      });

      pipelineTasksList.appendChild(card);
    });
  }

  function syncCurrentTasksFromUI() {
    if (!pipelineTasksList) return [];
    const updated = [];
    Array.from(pipelineTasksList.children).forEach((card, idx) => {
      const nameInput = card.querySelector(".phase-input-name");
      const descInput = card.querySelector(".phase-input-desc");
      const riskSelect = card.querySelector(".phase-select-risk");
      const skillsInput = card.querySelector(".phase-input-skills");
      const depsInput = card.querySelector(".phase-input-deps");

      const skillsRaw = skillsInput ? skillsInput.value.trim() : "";
      const depsRaw = depsInput ? depsInput.value.trim() : "";
      const skills = skillsRaw ? skillsRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
      const deps = depsRaw ? depsRaw.split(",").map(d => d.trim()).filter(Boolean) : [];

      updated.push({
        id: `t${idx + 1}`,
        name: nameInput ? nameInput.value.trim() || `Phase ${idx + 1}` : `Phase ${idx + 1}`,
        description: descInput ? descInput.value.trim() : "",
        required_skills: skills,
        dependencies: deps,
        risk_level: riskSelect ? riskSelect.value : "low",
      });
    });
    return updated;
  }

  if (openWorkflowBuilderBtn) {
    openWorkflowBuilderBtn.addEventListener("click", openWorkflowBuilderModal);
  }
  if (closeWorkflowBuilderBtn) {
    closeWorkflowBuilderBtn.addEventListener("click", closeWorkflowBuilderModal);
  }
  if (cancelWorkflowBuilderBtn) {
    cancelWorkflowBuilderBtn.addEventListener("click", closeWorkflowBuilderModal);
  }
  if (workflowBuilderModal) {
    workflowBuilderModal.addEventListener("click", (e) => {
      if (e.target === workflowBuilderModal) closeWorkflowBuilderModal();
    });
  }

  if (toggleWorkflowModeBtn) {
    toggleWorkflowModeBtn.addEventListener("click", () => {
      if (!isCustomWorkflowMode) {
        openWorkflowBuilderModal();
      } else {
        if (confirm("Switch back to Autonomous Auto-Plan mode?")) {
          isCustomWorkflowMode = false;
          updateWorkflowModeUI();
          showToast("Switched to Autonomous Auto-Plan mode.");
        } else {
          openWorkflowBuilderModal();
        }
      }
    });
  }

  if (tplSocBtn) {
    tplSocBtn.addEventListener("click", () => loadWorkflowTemplate("soc-5-phase-investigation"));
  }
  if (tplAuditBtn) {
    tplAuditBtn.addEventListener("click", () => loadWorkflowTemplate("code-vulnerability-audit"));
  }
  if (tplClearBtn) {
    tplClearBtn.addEventListener("click", () => {
      currentWorkflowTasks = [
        {
          id: "t1",
          name: "Initial Phase",
          description: "Execute primary investigation or analysis",
          required_skills: ["file_reading"],
          dependencies: [],
          risk_level: "low",
        },
      ];
      renderPipelineEditor(currentWorkflowTasks);
      updateTemplateButtonStates("blank");
    });
  }

  if (addPhaseBtn) {
    addPhaseBtn.addEventListener("click", () => {
      const current = syncCurrentTasksFromUI();
      const nextId = `t${current.length + 1}`;
      current.push({
        id: nextId,
        name: `Phase ${current.length + 1}`,
        description: "Describe phase objective...",
        required_skills: ["file_reading"],
        dependencies: current.length > 0 ? [`t${current.length}`] : [],
        risk_level: "low",
      });
      currentWorkflowTasks = current;
      renderPipelineEditor(currentWorkflowTasks);
    });
  }

  if (applyWorkflowBtn) {
    applyWorkflowBtn.addEventListener("click", () => {
      const compiledTasks = syncCurrentTasksFromUI();
      if (!compiledTasks.length) {
        showToast("Pipeline must have at least one phase", "error");
        return;
      }

      currentWorkflowTasks = compiledTasks;
      activeCustomDag = {
        goal: promptInput ? promptInput.value.trim() || "Custom Investigation Pipeline" : "Custom Pipeline",
        reasoning: "User-defined multi-phase pipeline with active supervisor ReAct evaluation",
        tasks: compiledTasks,
      };
      isCustomWorkflowMode = true;
      updateWorkflowModeUI();
      closeWorkflowBuilderModal();
      showToast(`Custom workflow pipeline active (${compiledTasks.length} phases)!`);
    });
  }

  // Pre-fetch workflow templates from API if available
  async function fetchWorkflowTemplates() {
    try {
      const res = await fetch("/api/workflows/templates");
      if (res.ok) {
        workflowTemplates = await res.json();
      }
    } catch (e) {
      workflowTemplates = BUILTIN_WORKFLOW_TEMPLATES;
    }
  }
  fetchWorkflowTemplates();

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // 9. Helpers
  function renderFinalSolution(markdownText, completedCount, failedCount) {
    solutionBody.innerHTML = formatMarkdown(markdownText);
    showToast(`Execution finished! ${completedCount} completed, ${failedCount} failed.`);
    const distillBtn = document.getElementById("distill-solution-btn");
    if (distillBtn && completedCount > 0 && !markdownText.includes("Execution Failed")) {
      distillBtn.style.display = "inline-flex";
    }
  }

  function renderSupervisorEvaluationsList(evalList) {
    if (!evalList || !Array.isArray(evalList)) return;
    evalList.forEach((evalObj) => {
      const tid = evalObj.task_id;
      let stepEl = document.getElementById(`step-${tid}`);
      if (!stepEl && activeDag) {
        const taskObj = (activeDag.tasks || []).find(t => t.id === tid);
        addTimelineStep(tid, taskObj ? taskObj.name : `Task ${tid}`, taskObj ? taskObj.description : "", "completed");
        stepEl = document.getElementById(`step-${tid}`);
      }
      if (stepEl) {
        let verdictEl = document.getElementById(`verdict-${tid}`);
        if (!verdictEl) {
          verdictEl = document.createElement("div");
          verdictEl.id = `verdict-${tid}`;
          const contentDiv = stepEl.querySelector(".step-content");
          if (contentDiv) contentDiv.appendChild(verdictEl);
        }
        const isPass = evalObj.decision === "pass" || evalObj.decision === "accurate" || evalObj.decision === "approved";
        const decision = isPass ? "pass" : "retry";
        const conf = evalObj.confidence !== undefined ? Math.round(evalObj.confidence * 100) : 100;
        verdictEl.className = `supervisor-verdict ${decision === "pass" ? "pass" : "retry"}`;
        verdictEl.innerHTML = `
          <div style="font-weight: 700; display: flex; justify-content: space-between; align-items: center;">
            <span>${decision === "pass" ? "🛡️ Supervisor Approved" : `🔄 Supervisor ReAct Retry (Attempt ${evalObj.retry_count || 1})`}</span>
            <span style="font-size: 11px; opacity: 0.85;">Confidence: ${conf}%</span>
          </div>
          <div style="font-size: 11px; margin-top: 4px; line-height: 1.4;">${escapeHtml(evalObj.feedback || "Task execution verified by Supervisor")}</div>
        `;
      }
    });
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
    const distillBtn = document.getElementById("distill-solution-btn");
    if (distillBtn) distillBtn.style.display = "none";
  }

  function setRunningState(isRunning) {
    solveBtn.disabled = isRunning;
    solveBtnText.textContent = isRunning ? "Executing Task..." : "Execute Task";
  }

  function formatMarkdown(text) {
    if (!text) return "";
    try {
      if (typeof marked !== "undefined") {
        if (typeof marked.setOptions === "function") {
          marked.setOptions({
            gfm: true,
            breaks: true,
          });
        }
        if (typeof marked.parse === "function") {
          return marked.parse(text);
        } else if (typeof marked === "function") {
          return marked(text);
        }
      }
    } catch (e) {
      console.warn("marked parsing error, using fallback:", e);
    }

    // Robust fallback parser
    let html = escapeHtml(text);
    // Fenced code blocks
    html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      return `<pre><code class="language-${lang}">${code}</code></pre>`;
    });
    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Headers
    html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
    html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
    html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");
    // Bold / italic
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    // Horizontal rules
    html = html.replace(/^---$/gm, "<hr>");
    // Tables fallback
    html = html.replace(/((?:\|[^\n]+\|\r?\n)+)/g, (match) => {
      const rows = match.trim().split("\n").map(r => r.trim()).filter(Boolean);
      if (rows.length < 2) return match;
      let tHtml = "<table>";
      rows.forEach((r, idx) => {
        if (r.match(/^\|(?:\s*:?-+:?\s*\|)+$/)) return;
        const cells = r.split("|").slice(1, -1).map(c => c.trim());
        const tag = idx === 0 ? "th" : "td";
        tHtml += `<tr>${cells.map(c => `<${tag}>${c}</${tag}>`).join("")}</tr>`;
      });
      tHtml += "</table>";
      return tHtml;
    });
    html = html.replace(/\n\n/g, "<p></p>").replace(/\n/g, "<br>");
    return html;
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
      switchIntegrationsTab(tabBtnTools);
      fetchTools();
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

  // Tab switching: Installed Tools, MCP, OpenAPI, Hermes
  const tabBtnTools = document.getElementById("tab-btn-tools");
  const tabBtnMcp = document.getElementById("tab-btn-mcp");
  const tabBtnOpenapi = document.getElementById("tab-btn-openapi");
  const tabBtnHermes = document.getElementById("tab-btn-hermes");
  const tabContentTools = document.getElementById("tab-content-tools");
  const tabContentMcp = document.getElementById("tab-content-mcp");
  const tabContentOpenapi = document.getElementById("tab-content-openapi");
  const tabContentHermes = document.getElementById("tab-content-hermes");

  function switchIntegrationsTab(activeTab) {
    const tabs = [
      { btn: tabBtnTools, content: tabContentTools },
      { btn: tabBtnMcp, content: tabContentMcp },
      { btn: tabBtnOpenapi, content: tabContentOpenapi },
      { btn: tabBtnHermes, content: tabContentHermes }
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

    if (activeTab === tabBtnHermes) {
      fetchHermesStats();
      fetchHermesCapabilities();
      fetchHermesHubSkills(hermesCurrentPage || 1);
    }
  }

  if (tabBtnTools) tabBtnTools.addEventListener("click", () => switchIntegrationsTab(tabBtnTools));
  if (tabBtnMcp) tabBtnMcp.addEventListener("click", () => switchIntegrationsTab(tabBtnMcp));
  if (tabBtnOpenapi) tabBtnOpenapi.addEventListener("click", () => switchIntegrationsTab(tabBtnOpenapi));
  if (tabBtnHermes) tabBtnHermes.addEventListener("click", () => switchIntegrationsTab(tabBtnHermes));

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
      const skillSet = new Set();
      if (res.ok) {
        const tools = await res.json();
        tools.forEach((t) => {
          (t.skills_provided || []).forEach((s) => {
            if (s && s.length >= 3 && !["and", "the", "for", "with", "this", "that"].includes(s.toLowerCase())) {
              skillSet.add(s.trim());
            }
          });
        });
      }

      // Also ensure all cataloged skills are included
      try {
        const catRes = await fetch("/api/skills/catalog");
        if (catRes.ok) {
          const cat = await catRes.json();
          (cat || []).forEach((c) => {
            if (c.name) skillSet.add(c.name.trim());
            (c.skills || []).forEach((s) => {
              if (s && s.length >= 3) skillSet.add(s.trim());
            });
          });
        }
      } catch (_) {}

      cachedSkillsList = Array.from(skillSet).sort((a, b) => a.localeCompare(b));
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
      aiGenerateAgentBtn.textContent = "✨ Designing with AI...";

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
          showToast("Agent profile synthesized by AI! Review and save below.", "success");
        } else {
          const errData = await res.json().catch(() => null);
          const errMsg = (errData && errData.detail) || `Server returned error (${res.status})`;
          console.error("AI Auto-Design failed:", errMsg);
          showToast(`AI Auto-Design failed: ${errMsg}`, "error");
        }
      } catch (err) {
        console.error("AI Auto-Design network error:", err);
        showToast(`AI Auto-Design network error: ${err.message}. Check if AgentHub server is online.`, "error");
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
          showToast("Python tool code generated by AI! Review & click Register.", "success");
        } else {
          const errData = await res.json().catch(() => null);
          const errMsg = (errData && errData.detail) || `Server returned error (${res.status})`;
          console.error("AI Skill generation failed:", errMsg);
          showToast(`Tool code generation failed: ${errMsg}`, "error");
        }
      } catch (err) {
        console.error("Skill generation network error:", err);
        showToast(`Skill generation network error: ${err.message}. Check if AgentHub server is online.`, "error");
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

  // ── Hermes Skills Catalog & Importer ───────────────────────────
  const hermesSkillContent = document.getElementById("hermes-skill-content") || document.getElementById("hermes-skill-input");
  const hermesImportBtn = document.getElementById("hermes-import-btn");
  const hermesImportStatus = document.getElementById("hermes-import-status") || document.getElementById("hermes-status");
  const hermesCatalogList = document.getElementById("hermes-catalog-list");
  const hermesCatalogCount = document.getElementById("hermes-catalog-count");

  const hermesPresets = {
    forensics: `---
name: oss_forensics
description: Forensically analyze open source packages for supply chain malware, obfuscated code, and tampering.
author: Nous Research / Hermes Security
version: 1.2.0
metadata:
  category: security
  skills: [oss_forensics, malware_analysis, supply_chain_security]
  risk_level: high
parameters:
  package_name: { type: string, description: Package name or repo URL, required: true }
  ecosystem: { type: string, description: pypi / npm / cargo, default: pypi }
---
# OSS Forensics Skill 🛡️
Inspects setup hooks, obfuscated eval patterns, and network exfiltration vectors.`,

    gitnexus: `---
name: gitnexus_explorer
description: Deep codebase architecture reconstruction, call graph topology extraction, and dependency tracing.
author: Nous Research / Hermes Research
version: 1.1.0
metadata:
  category: research
  skills: [gitnexus_explorer, code_analysis, architecture_recovery]
  risk_level: low
parameters:
  repo_path: { type: string, description: Path to repository, required: true }
  focus_module: { type: string, description: Primary module to trace }
---
# GitNexus Explorer Skill 🔍
Reconstructs architectural topology and generates Mermaid dependency graphs.`,

    instructor: `---
name: instructor_mlops
description: Extract structured JSON data with strict Pydantic schemas, validation rules, and self-correcting retries.
author: Nous Research / Hermes MLOps
version: 1.3.0
metadata:
  category: mlops
  skills: [instructor_mlops, structured_output, pydantic, json_extraction]
  risk_level: low
parameters:
  unstructured_text: { type: string, description: Raw text to extract from, required: true }
  schema_definition: { type: string, description: Pydantic schema specification, required: true }
---
# Instructor MLOps Skill 🤖
Enforces strict types and feeds validation tracebacks back to the LLM for self-correction.`,

    drug: `---
name: drug_discovery
description: Computational cheminformatics: parse chemical SMILES representations, compute descriptors, and bioactivity.
author: Nous Research / Hermes Science
version: 1.0.0
metadata:
  category: research
  skills: [drug_discovery, cheminformatics, smiles, bioactivity]
  risk_level: low
parameters:
  smiles_string: { type: string, description: SMILES chemical structure, required: true }
  calculate_lipinski: { type: boolean, description: Calculate Rule of Five metrics, default: true }
---
# Drug Discovery Skill 🧬
Analyzes chemical candidates and pharmacokinetic drug-likeness.`,

    design: `---
name: impeccable_design
description: Audit web applications, design systems, and components for visual hierarchy, typography, and WCAG accessibility.
author: Nous Research / Hermes Creative
version: 1.2.0
metadata:
  category: creative
  skills: [impeccable_design, ui_ux, design_audit, accessibility]
  risk_level: low
parameters:
  component_html: { type: string, description: HTML/CSS markup to critique, required: true }
  target_aesthetic: { type: string, description: Target aesthetic, default: sleek dark mode }
---
# Impeccable Design Skill 🎨
Audits visual hierarchy, glassmorphism, spatial rhythm, and contrast ratios.`,

    airtable: `---
name: airtable_crm
description: Query, filter, and mutate records across Airtable bases and CRM tables via Airtable REST API.
author: Nous Research / Hermes Productivity
version: 1.0.0
metadata:
  category: productivity
  skills: [airtable_crm, database_query, crm_management]
  risk_level: medium
parameters:
  base_id: { type: string, description: Airtable Base ID, required: true }
  table_name: { type: string, description: Table name, required: true }
  action: { type: string, description: list / create / update, default: list }
---
# Airtable CRM Skill 📋
Enables Universal Workers to query and update CRM records.`,

    diagram: `---
name: architecture_diagram
description: Generate visual Mermaid architecture and cloud infrastructure diagrams from system descriptions.
author: Nous Research / Hermes Engineering
version: 1.1.0
metadata:
  category: creative
  skills: [architecture_diagram, diagram_generation, architecture_design]
  risk_level: low
parameters:
  system_description: { type: string, description: Description of components and data flow, required: true }
  diagram_type: { type: string, description: graph TD or sequenceDiagram, default: graph TD }
---
# Architecture Diagram Skill 📊
Transforms component interactions into structured Mermaid diagrams.`,

    herenow: `---
name: here_now
description: Real-time contextual briefing: compute local sunrise/sunset, timezone offsets, and weather forecasts.
author: Nous Research / Hermes Productivity
version: 1.1.0
metadata:
  category: productivity
  skills: [here_now, weather, timezone, local_intelligence]
  risk_level: low
parameters:
  location: { type: string, description: Target city or coordinates, required: true }
---
# Here Now Skill 🌐
Provides real-time local intelligence and operational context.`,

    fitness: `---
name: fitness_nutrition
description: Quantitative nutritional science: calculate basal metabolic rate (BMR), TDEE, and macronutrient partitioning.
author: Nous Research / Hermes Health
version: 1.0.0
metadata:
  category: health
  skills: [fitness_nutrition, metabolic_calculation, macronutrient_planning]
  risk_level: low
parameters:
  body_weight_kg: { type: number, description: Weight in kg, required: true }
  height_cm: { type: number, description: Height in cm, required: true }
---
# Fitness & Nutrition Skill 🥗
Calculates metabolic expenditure and macronutrient gram distributions.`,

    delegation: `---
name: subagent_delegation
description: Decompose massive multi-phase objectives and spawn isolated Universal Worker subagents with dedicated scopes.
author: Nous Research / Hermes Orchestration
version: 1.5.0
metadata:
  category: orchestration
  skills: [subagent_delegation, multi_agent_orchestration, task_decomposition]
  risk_level: medium
parameters:
  subtask_goal: { type: string, description: Subagent objective, required: true }
---
# Subagent Delegation Skill 👥
Spawns independent worker processes to collapse complex multi-turn problems.`,

    arxiv: `---
name: arxiv_research
description: Search ArXiv preprints, download abstracts, parse LaTeX math equations, and summarize frontier machine learning research.
author: Nous Research / Research Hub
version: 1.0.0
metadata:
  category: research
  skills: [arxiv_research, paper_search, literature_review, ml_research]
  risk_level: low
parameters:
  query: { type: string, description: ArXiv search query or topic, required: true }
---
# ArXiv Research & Synthesis Skill 📚
Extracts state-of-the-art machine learning preprints and mathematical formulations.`,

    simplify: `---
name: simplify_code
description: Refactor convoluted functions, eliminate redundant abstractions, reduce cyclomatic complexity, and improve readability.
author: Nous Research / Engineering
version: 1.0.0
metadata:
  category: software-development
  skills: [simplify_code, code_refactoring, clean_code, complexity_reduction]
  risk_level: low
parameters:
  code_snippet: { type: string, description: Source code to refactor, required: true }
---
# Code Simplification & Refactoring Skill ✂️
Enforces idiomatic structure, guard clauses, and verified equivalence.`,

    computer: `---
name: computer_use
description: Autonomous desktop and browser coordinate automation, screenshot vision grounding, and keystroke dispatch.
author: Nous Research / Autonomous Agent Core
version: 1.0.0
metadata:
  category: autonomous-ai-agents
  skills: [computer_use, gui_automation, screenshot_grounding, desktop_control]
  risk_level: medium
parameters:
  target_action: { type: string, description: click / type / scroll / capture, required: true }
---
# Computer Use & Desktop Control Skill 🖥️
Performs vision-grounded coordinate interactions and desktop navigation.`,

    claude: `---
name: claude_code
description: Deep pair programming with automated test-driven iteration, file navigation, and rigorous code verification.
author: Nous Research / Developer Tools
version: 1.0.0
metadata:
  category: autonomous-ai-agents
  skills: [claude_code, pair_programming, test_driven_dev, codebase_search]
  risk_level: medium
parameters:
  feature_spec: { type: string, description: Specification of feature or bug to fix, required: true }
---
# Claude-Code Style Autonomous Coding Skill 💻
Enforces test-first reproduction and surgical diff application.`,

    docker: `---
name: docker_ops
description: Inspect running containers, debug failing builds, optimize Dockerfile layers, and orchestrate Docker Compose stacks.
author: Nous Research / DevOps
version: 1.0.0
metadata:
  category: devops
  skills: [docker_ops, container_management, docker_compose, devops_troubleshooting]
  risk_level: high
parameters:
  command_target: { type: string, description: Container name or compose service, required: true }
---
# Docker Operations & Containerization Skill 🐳
Streamlines multi-stage builds, layer caching, and container health audits.`,

    github: `---
name: github_workflow
description: Automate GitHub PR creation, analyze CI/CD GitHub Actions workflow runs, and generate release changelogs.
author: Nous Research / Developer Tools
version: 1.0.0
metadata:
  category: developer-tools
  skills: [github_workflow, pull_requests, ci_cd_debug, release_notes]
  risk_level: medium
parameters:
  repo: { type: string, description: GitHub owner/repo format, required: true }
---
# GitHub Workflow & CI/CD Automation Skill 🐙
Automates PR metadata, CI log analysis, and release notes.`,

    database: `---
name: database_optimizer
description: Analyze PostgreSQL and SQLite query plans, diagnose slow sequential scans, identify missing indexes, and resolve N+1 queries.
author: Nous Research / Database Engineering
version: 1.0.0
metadata:
  category: database
  skills: [database_optimizer, sql_tuning, explain_analyze, index_optimization]
  risk_level: medium
parameters:
  sql_query: { type: string, description: Slow SQL query or schema to optimize, required: true }
---
# Database Performance & SQL Optimization Skill ⚡
Detects unindexed table scans, joins, and ORM query overhead.`,

    notes: `---
name: apple_notes
description: Create, search, update, and format rich notes, markdown journals, and knowledge bases with Apple Notes & local folders.
author: Nous Research / Productivity
version: 1.0.0
metadata:
  category: productivity
  skills: [apple_notes, note_taking, knowledge_base, markdown_notes]
  risk_level: low
parameters:
  title: { type: string, description: Note title, required: true }
  content: { type: string, description: Note markdown body, required: true }
---
# Apple Notes & Knowledge Base Synchronization Skill 📝
Drafts structured meeting minutes and long-term project knowledge.`,

    reminders: `---
name: apple_reminders
description: Parse natural language tasks into scheduled reminders with deadlines, priority tags, and recurring alarm triggers.
author: Nous Research / Productivity
version: 1.0.0
metadata:
  category: productivity
  skills: [apple_reminders, task_scheduling, deadline_tracking, reminder_alerts]
  risk_level: low
parameters:
  task: { type: string, description: Natural language task description, required: true }
---
# Apple Reminders & Task Dispatch Skill ⏰
Parses natural language times and dispatches alarms and due dates.`,

    discord: `---
name: discord_notifier
description: Format rich Discord webhook embeds, broadcast agent status updates, error alerts, and workflow execution summaries.
author: Nous Research / Communications
version: 1.0.0
metadata:
  category: communication
  skills: [discord_notifier, webhook_alerts, chat_notifications, embed_builder]
  risk_level: low
parameters:
  message: { type: string, description: Summary message, required: true }
---
# Discord Webhook & Agent Notification Skill 💬
Dispatches rich color-coded status embeds to team channels.`,

    ascii: `---
name: ascii_art
description: Render stylish terminal ASCII banners, ANSI color diagrams, retro typography, and CLI status dashboards.
author: Nous Research / Creative
version: 1.0.0
metadata:
  category: creative
  skills: [ascii_art, terminal_graphics, ansi_banners, cli_typography]
  risk_level: low
parameters:
  text: { type: string, description: Text banner or diagram label, required: true }
---
# ASCII Art & Terminal Graphics Skill 👾
Renders clean 80-column Unicode box-drawing banners and CLI status badges.`,

    homeassistant: `---
name: home_assistant
description: Inspect IoT entity states, trigger scenes, adjust climate/lights, and automate smart home devices via Home Assistant REST API.
author: Nous Research / IoT Integrations
version: 1.0.0
metadata:
  category: integrations
  skills: [home_assistant, iot_automation, smart_home, rest_api]
  risk_level: medium
parameters:
  domain: { type: string, description: Domain (e.g. light, switch, climate), required: true }
  action: { type: string, description: turn_on / turn_off / get_state, required: true }
---
# Home Assistant IoT Automation Skill 🏠
Integrates with smart home sensors, switches, lighting, and scenes.`
  };

  // Wire all preset chip buttons
  const presetMap = [
    { id: "preset-hermes-forensics", key: "forensics", label: "OSS Forensics" },
    { id: "preset-hermes-gitnexus", key: "gitnexus", label: "GitNexus Explorer" },
    { id: "preset-hermes-instructor", key: "instructor", label: "Instructor MLOps" },
    { id: "preset-hermes-drug", key: "drug", label: "Drug Discovery" },
    { id: "preset-hermes-design", key: "design", label: "Impeccable Design" },
    { id: "preset-hermes-airtable", key: "airtable", label: "Airtable CRM" },
    { id: "preset-hermes-diagram", key: "diagram", label: "Architecture Diagram" },
    { id: "preset-hermes-herenow", key: "herenow", label: "Here Now" },
    { id: "preset-hermes-fitness", key: "fitness", label: "Fitness & Nutrition" },
    { id: "preset-hermes-delegation", key: "delegation", label: "Subagent Delegation" },
    { id: "preset-hermes-arxiv", key: "arxiv", label: "ArXiv Research" },
    { id: "preset-hermes-simplify", key: "simplify", label: "Simplify Code" },
    { id: "preset-hermes-computer", key: "computer", label: "Computer Use" },
    { id: "preset-hermes-claude", key: "claude", label: "Claude-Code CLI" },
    { id: "preset-hermes-docker", key: "docker", label: "Docker Ops" },
    { id: "preset-hermes-github", key: "github", label: "GitHub Workflow" },
    { id: "preset-hermes-database", key: "database", label: "Database Optimizer" },
    { id: "preset-hermes-notes", key: "notes", label: "Apple Notes" },
    { id: "preset-hermes-reminders", key: "reminders", label: "Apple Reminders" },
    { id: "preset-hermes-discord", key: "discord", label: "Discord Notifier" },
    { id: "preset-hermes-ascii", key: "ascii", label: "ASCII Art" },
    { id: "preset-hermes-homeassistant", key: "homeassistant", label: "Home Assistant" },
  ];

  presetMap.forEach(({ id, key, label }) => {
    const el = document.getElementById(id);
    if (el && hermesSkillContent) {
      el.addEventListener("click", () => {
        hermesSkillContent.value = hermesPresets[key];
        showToast(`Loaded ${label} specification from Skills Catalog`);
      });
    }
  });

  // ── Hermes Skills Hub & Capabilities Engine (97,986 Skills Index) ────
  let hermesCurrentQuery = "";
  let hermesCurrentCat = "all";
  let hermesCurrentReg = "all";
  let hermesCurrentPage = 1;
  const hermesPageLimit = 24;
  let hermesTotalSkills = 97986;
  let hermesInstalledCapabilities = [];
  let hermesSelectedCapability = null;
  let hermesDebounceTimer = null;

  const hermesSearchInput = document.getElementById("hermes-search-input");
  const hermesRegistryChips = document.getElementById("hermes-registry-chips");
  const hermesSidebar = document.getElementById("hermes-sidebar");
  const hermesSkillsGrid = document.getElementById("hermes-skills-grid");
  const hermesPageInfo = document.getElementById("hermes-page-info");
  const hermesPrevPageBtn = document.getElementById("hermes-prev-page");
  const hermesNextPageBtn = document.getElementById("hermes-next-page");
  const capabilitiesList = document.getElementById("capabilities-list");
  const capInspTitle = document.getElementById("cap-insp-title");
  const capInspDesc = document.getElementById("cap-insp-desc");
  const capInspMeta = document.getElementById("cap-insp-meta");
  const capSkillsCount = document.getElementById("cap-skills-count");
  const capToolsCount = document.getElementById("cap-tools-count");
  const toggleCustomSkillBtn = document.getElementById("toggle-custom-skill-btn");
  const customSkillContainer = document.getElementById("custom-skill-container");

  if (toggleCustomSkillBtn && customSkillContainer) {
    toggleCustomSkillBtn.addEventListener("click", () => {
      const isHidden = customSkillContainer.style.display === "none";
      customSkillContainer.style.display = isHidden ? "block" : "none";
      toggleCustomSkillBtn.textContent = isHidden ? "- Hide Custom Spec Form" : "+ Paste Custom SKILL.md";
    });
  }

  // Press "/" to focus search bar (as requested in Hermes Desktop)
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== hermesSearchInput && !["INPUT", "TEXTAREA"].includes((document.activeElement && document.activeElement.tagName) || "")) {
      if (tabContentHermes && tabContentHermes.style.display !== "none") {
        e.preventDefault();
        hermesSearchInput && hermesSearchInput.focus();
      }
    }
  });

  async function fetchHermesStats() {
    try {
      const res = await fetch("/api/skills/ecosystem/stats");
      if (!res.ok) return;
      const stats = await res.json();
      if (stats.builtin !== undefined) {
        const bEl = document.getElementById("stat-builtin");
        if (bEl) bEl.textContent = stats.builtin;
      }
      if (stats.optional !== undefined) {
        const oEl = document.getElementById("stat-optional");
        if (oEl) oEl.textContent = stats.optional;
      }
      if (stats.community !== undefined) {
        const cEl = document.getElementById("stat-community");
        if (cEl) cEl.textContent = stats.community.toLocaleString();
      }
      if (stats.categories !== undefined) {
        const catEl = document.getElementById("stat-categories");
        if (catEl) catEl.textContent = stats.categories;
      }
    } catch (e) {
      console.warn("Could not fetch ecosystem stats:", e);
    }
  }

  async function fetchHermesCapabilities() {
    if (!capabilitiesList) return;
    try {
      const res = await fetch("/api/skills/capabilities");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      hermesInstalledCapabilities = await res.json();

      if (capSkillsCount) capSkillsCount.textContent = hermesInstalledCapabilities.length;
      const registeredTools = document.querySelectorAll("#tool-list .tool-card");
      if (capToolsCount) capToolsCount.textContent = (registeredTools && registeredTools.length) || 25;

      if (!hermesInstalledCapabilities || hermesInstalledCapabilities.length === 0) {
        capabilitiesList.innerHTML = `
          <div style="text-align: center; padding: 18px; color: var(--text-dim); font-size: 12px;">
            No capabilities active yet. Install skills from the catalog below.
          </div>
        `;
        return;
      }

      capabilitiesList.innerHTML = hermesInstalledCapabilities.map((c, idx) => {
        const isSelected = (!hermesSelectedCapability && idx === 0) || (hermesSelectedCapability && hermesSelectedCapability.name === c.name);
        if (isSelected && !hermesSelectedCapability) hermesSelectedCapability = c;
        return `
          <div class="capability-item ${isSelected ? 'selected' : ''}" data-name="${escapeHtml(c.name)}">
            <div class="capability-name-col">
              <span class="capability-name">${escapeHtml(c.name)}</span>
              <span class="capability-cat-tag">${escapeHtml(c.category || 'Productivity')}</span>
            </div>
            <label class="switch-toggle" onclick="event.stopPropagation();">
              <input type="checkbox" class="cap-toggle-input" data-name="${escapeHtml(c.name)}" checked>
              <span class="slider-round"></span>
            </label>
          </div>
        `;
      }).join("");

      // Wire capability selection
      capabilitiesList.querySelectorAll(".capability-item").forEach(item => {
        item.addEventListener("click", () => {
          const name = item.getAttribute("data-name");
          const cap = hermesInstalledCapabilities.find(c => c.name === name);
          if (cap) selectHermesCapability(cap);
        });
      });

      // Wire toggles
      capabilitiesList.querySelectorAll(".cap-toggle-input").forEach(toggle => {
        toggle.addEventListener("change", () => {
          const name = toggle.getAttribute("data-name");
          showToast(`Capability '${name}' ${toggle.checked ? 'enabled' : 'disabled'} for upcoming sessions`);
        });
      });

      if (hermesSelectedCapability) {
        selectHermesCapability(hermesSelectedCapability);
      } else if (hermesInstalledCapabilities[0]) {
        selectHermesCapability(hermesInstalledCapabilities[0]);
      }
    } catch (e) {
      console.warn("Could not fetch installed capabilities:", e);
    }
  }

  function selectHermesCapability(cap) {
    if (!cap) return;
    hermesSelectedCapability = cap;
    if (capabilitiesList) {
      capabilitiesList.querySelectorAll(".capability-item").forEach(el => {
        if (el.getAttribute("data-name") === cap.name) {
          el.classList.add("selected");
        } else {
          el.classList.remove("selected");
        }
      });
    }

    if (capInspTitle) {
      capInspTitle.innerHTML = `
        <span>${escapeHtml(cap.title || cap.name)}</span>
        <span class="capability-cat-tag">${escapeHtml(cap.category || 'Productivity')}</span>
      `;
    }
    if (capInspDesc) {
      capInspDesc.textContent = cap.description || "No description provided.";
    }
    if (capInspMeta) {
      const paramsList = Object.keys(cap.parameters || {}).length > 0 
        ? Object.entries(cap.parameters).map(([k, v]) => `  ${k}: ${v.description || v.type || 'string'}`).join("\n")
        : "  (no parameters required)";
      capInspMeta.innerHTML = `name: ${escapeHtml(cap.name)}<br>description: ${escapeHtml(cap.description || '')}<br>parameters:<br><span style="color:#93c5fd; white-space: pre;">${escapeHtml(paramsList)}</span>`;
    }
  }

  async function fetchHermesHubSkills(page = 1) {
    if (!hermesSkillsGrid) return;
    hermesCurrentPage = page;
    hermesSkillsGrid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 32px; color: var(--text-dim); font-size: 13px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" style="animation: spin 1s linear infinite; margin-bottom: 8px;">
          <circle cx="12" cy="12" r="10" stroke-dasharray="30" stroke-dashoffset="10"/>
        </svg>
        <div>Querying 97,986 skills ecosystem across 12 registries...</div>
      </div>
    `;

    try {
      const url = `/api/skills/ecosystem/search?q=${encodeURIComponent(hermesCurrentQuery)}&category=${encodeURIComponent(hermesCurrentCat)}&registry=${encodeURIComponent(hermesCurrentReg)}&page=${page}&limit=${hermesPageLimit}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const skills = data.skills || [];
      hermesTotalSkills = data.total || 97986;

      // Update page info
      const from = (page - 1) * hermesPageLimit + 1;
      const to = Math.min(page * hermesPageLimit, hermesTotalSkills);
      if (hermesPageInfo) {
        hermesPageInfo.textContent = `Showing ${from.toLocaleString()} - ${to.toLocaleString()} of ${hermesTotalSkills.toLocaleString()} skills`;
      }

      if (hermesPrevPageBtn) hermesPrevPageBtn.disabled = page <= 1;
      if (hermesNextPageBtn) hermesNextPageBtn.disabled = to >= hermesTotalSkills;

      if (!skills || skills.length === 0) {
        hermesSkillsGrid.innerHTML = `
          <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-dim);">
            <div style="font-size: 1.8rem; margin-bottom: 6px;">🔍</div>
            <div style="font-size: 14px; font-weight: 600; color: #fff;">No matching skills found</div>
            <div style="font-size: 12px; margin-top: 4px;">Try adjusting your search terms or filter criteria.</div>
          </div>
        `;
        return;
      }

      hermesSkillsGrid.innerHTML = skills.map((s) => {
        let badgeClass = "hermes-badge-community";
        let badgeText = s.registry_label || "Community";
        if (s.registry === "builtin" || s.registry_label === "Built-in") {
          badgeClass = "hermes-badge-builtin";
          badgeText = "✔ Built-in";
        } else if (s.registry === "optional" || s.registry_label === "Optional") {
          badgeClass = "hermes-badge-optional";
          badgeText = "Optional";
        }

        const tagsHtml = (s.tags || [s.category || 'Skill'])
          .slice(0, 3)
          .map(t => `<span class="hermes-tag">${escapeHtml(t)}</span>`)
          .join("");

        const isInstalled = s.installed || hermesInstalledCapabilities.some(c => c.name === s.name || c.name === s.name.replace(/-/g, "_"));

        return `
          <div class="hermes-card" data-name="${escapeHtml(s.name)}">
            <div>
              <div class="hermes-card-top">
                <span class="hermes-card-title">${escapeHtml(s.title || s.name)}</span>
                <span class="${badgeClass}">${escapeHtml(badgeText)}</span>
              </div>
              <div class="hermes-card-desc" title="${escapeHtml(s.description)}">${escapeHtml(s.description)}</div>
              <div class="hermes-card-tags">${tagsHtml}</div>
            </div>
            <div>
              <button type="button" class="hermes-btn-add ${isInstalled ? 'installed' : ''}" data-skill='${JSON.stringify(s).replace(/'/g, "&apos;")}'>
                ${isInstalled ? '✔ Added' : '+ Add to this Agent'}
              </button>
            </div>
          </div>
        `;
      }).join("");

      // Wire "+ Add to this Agent" install buttons
      hermesSkillsGrid.querySelectorAll(".hermes-btn-add").forEach(btn => {
        if (btn.classList.contains("installed")) return;
        btn.addEventListener("click", async () => {
          const raw = btn.getAttribute("data-skill");
          if (!raw) return;
          const sData = JSON.parse(raw.replace(/&apos;/g, "'"));
          btn.disabled = true;
          btn.textContent = "Installing...";

          try {
            const installRes = await fetch("/api/skills/ecosystem/install", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(sData),
            });
            if (!installRes.ok) throw new Error(`HTTP ${installRes.status}`);
            const installed = await installRes.json();
            showToast(`Installed '${installed.title || installed.name}' into Agent Skills Registry!`, "success");
            btn.classList.add("installed");
            btn.textContent = "✔ Added";
            btn.disabled = true;

            await fetchHermesCapabilities();
            fetchTools();
            fetchHealth();
            populateSkillsPicker();
          } catch (err) {
            showToast(`Installation failed: ${err.message}`, "error");
            btn.disabled = false;
            btn.textContent = "+ Add to this Agent";
          }
        });
      });

    } catch (err) {
      console.warn("Hermes skills search error:", err);
    }
  }

  // Registry Chips Click Handler
  if (hermesRegistryChips) {
    hermesRegistryChips.querySelectorAll(".hermes-reg-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        hermesRegistryChips.querySelectorAll(".hermes-reg-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        hermesCurrentReg = chip.getAttribute("data-reg") || "all";
        fetchHermesHubSkills(1);
      });
    });
  }

  // Sidebar Categories Click Handler
  if (hermesSidebar) {
    hermesSidebar.querySelectorAll(".hermes-cat-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        hermesSidebar.querySelectorAll(".hermes-cat-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        hermesCurrentCat = btn.getAttribute("data-cat") || "all";
        fetchHermesHubSkills(1);
      });
    });
  }

  // Debounced Search Input
  if (hermesSearchInput) {
    hermesSearchInput.addEventListener("input", () => {
      clearTimeout(hermesDebounceTimer);
      hermesDebounceTimer = setTimeout(() => {
        hermesCurrentQuery = hermesSearchInput.value.trim();
        fetchHermesHubSkills(1);
      }, 250);
    });
  }

  // Pagination Next / Prev
  if (hermesPrevPageBtn) {
    hermesPrevPageBtn.addEventListener("click", () => {
      if (hermesCurrentPage > 1) {
        fetchHermesHubSkills(hermesCurrentPage - 1);
      }
    });
  }

  if (hermesNextPageBtn) {
    hermesNextPageBtn.addEventListener("click", () => {
      fetchHermesHubSkills(hermesCurrentPage + 1);
    });
  }

  if (hermesImportBtn && hermesSkillContent) {
    hermesImportBtn.addEventListener("click", async () => {
      const content = hermesSkillContent.value.trim();
      if (!content) {
        showToast("Please enter a SKILL.md definition first", "error");
        return;
      }

      hermesImportBtn.disabled = true;
      hermesImportBtn.textContent = "⚡ Registering Skill...";
      if (hermesImportStatus) hermesImportStatus.style.display = "none";

      try {
        const res = await fetch("/api/skills/import/hermes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: content, persist: true }),
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => null);
          throw new Error((errData && errData.detail) || `HTTP ${res.status}`);
        }

        const data = await res.json();
        if (hermesImportStatus) {
          hermesImportStatus.style.display = "block";
          hermesImportStatus.style.background = "rgba(16, 185, 129, 0.2)";
          hermesImportStatus.style.color = "#34d399";
          hermesImportStatus.textContent = `✔ Skill '${data.name}' registered and converted to ToolSpec!`;
        }

        showToast(`Skill '${data.name}' registered!`);
        fetchHermesCatalog();
        fetchTools();
        fetchHealth();
        populateSkillsPicker();
      } catch (err) {
        if (hermesImportStatus) {
          hermesImportStatus.style.display = "block";
          hermesImportStatus.style.background = "rgba(244, 63, 94, 0.15)";
          hermesImportStatus.style.color = "#fda4af";
          hermesImportStatus.textContent = `✖ Import failed: ${err.message}`;
        }
        showToast(`Import error: ${err.message}`, "error");
      } finally {
        hermesImportBtn.disabled = false;
        hermesImportBtn.textContent = "⚡ Register Skill into Engine";
      }
    });
  }

  // ── Scheduled Workflows Modal & Management ────────────────────────
  const schedulesModal = document.getElementById("schedules-modal");
  const openSchedulesBtn = document.getElementById("open-schedules-btn");
  const closeSchedulesModalX = document.getElementById("close-schedules-modal-x");
  const closeSchedulesModalBtn = document.getElementById("close-schedules-modal-btn");
  const activeSchedulesBadge = document.getElementById("schedules-count") || document.getElementById("active-schedules-badge");
  const schedulesList = document.getElementById("schedules-list");
  const schedulesListCount = document.getElementById("schedules-list-count");
  const scheduleForm = document.getElementById("schedule-form");
  const schedName = document.getElementById("sched-name");
  const schedCron = document.getElementById("sched-cron");
  const schedQuery = document.getElementById("sched-query");
  const schedEnabled = document.getElementById("sched-enabled");

  async function updateSchedulesBadge() {
    if (!activeSchedulesBadge) return;
    try {
      const res = await fetch("/api/schedules");
      if (res.ok) {
        const jobs = await res.json();
        const activeCount = (jobs || []).filter((j) => j.enabled).length;
        activeSchedulesBadge.textContent = activeCount;
        activeSchedulesBadge.style.display = activeCount > 0 ? "inline-block" : "none";
      }
    } catch (_) {}
  }

  async function fetchSchedules() {
    if (!schedulesList) return;
    try {
      const res = await fetch("/api/schedules");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const jobs = await res.json();

      if (schedulesListCount) schedulesListCount.textContent = (jobs || []).length;
      updateSchedulesBadge();

      if (!jobs || jobs.length === 0) {
        schedulesList.innerHTML = `
          <div style="text-align: center; padding: 24px; color: var(--text-dim); font-size: 13px;">
            No recurring schedules created yet. Create a schedule above!
          </div>
        `;
        return;
      }

      schedulesList.innerHTML = jobs.map((job) => {
        const statusClass = job.enabled ? "online" : "degraded";
        const statusText = job.enabled ? "Active" : "Paused";
        const toggleBtnText = job.enabled ? "⏸️ Pause" : "▶️ Resume";
        const toggleStyle = job.enabled
          ? "background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3);"
          : "background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);";

        let nextRunText = "Calculating...";
        if (job.next_run) {
          try {
            nextRunText = new Date(job.next_run).toLocaleString();
          } catch (_) {
            nextRunText = job.next_run;
          }
        }

        return `
          <div class="tool-card" style="display: flex; flex-direction: column; gap: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-weight: 700; color: #fff; font-size: 14px;">${escapeHtml(job.name)}</span>
                <span class="status-pill ${statusClass}" style="padding: 2px 8px; font-size: 11px;">
                  <span class="dot"></span>
                  <span class="status-label">${statusText}</span>
                </span>
              </div>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button type="button" class="btn-card-use toggle-schedule-btn" data-id="${job.id}" style="${toggleStyle} font-size: 11px; padding: 4px 10px;">
                  ${toggleBtnText}
                </button>
                <button type="button" class="btn-card-icon delete-schedule-btn" data-id="${job.id}" data-name="${escapeHtml(job.name)}" title="Delete Schedule" style="color: #ef4444; font-size: 13px;">
                  ✕
                </button>
              </div>
            </div>

            <div style="display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--text-muted);">
              <span style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-weight: 600;">
                ⏱️ ${escapeHtml(job.cron_expression)}
              </span>
              <span>Next: ${nextRunText}</span>
              <span>Runs: ${job.run_count || 0}</span>
            </div>

            <div style="font-size: 12px; color: var(--text-dim); background: rgba(0, 0, 0, 0.25); padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.05); font-family: 'JetBrains Mono', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
              ${escapeHtml(job.query)}
            </div>
          </div>
        `;
      }).join("");

      // Wire up toggle buttons
      document.querySelectorAll(".toggle-schedule-btn").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const jobId = btn.getAttribute("data-id");
          try {
            const res = await fetch(`/api/schedules/${jobId}/toggle`, { method: "POST" });
            if (!res.ok) throw new Error("Toggle failed");
            fetchSchedules();
          } catch (err) {
            showToast(`Error toggling schedule: ${err.message}`, "error");
          }
        });
      });

      // Wire up delete buttons
      document.querySelectorAll(".delete-schedule-btn").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const jobId = btn.getAttribute("data-id");
          const jobName = btn.getAttribute("data-name");
          if (!confirm(`Delete recurring schedule '${jobName}'?`)) return;
          try {
            const res = await fetch(`/api/schedules/${jobId}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Delete failed");
            showToast(`Schedule '${jobName}' deleted`);
            fetchSchedules();
          } catch (err) {
            showToast(`Error deleting schedule: ${err.message}`, "error");
          }
        });
      });
    } catch (err) {
      console.warn("Could not fetch schedules:", err);
    }
  }

  if (openSchedulesBtn && schedulesModal) {
    openSchedulesBtn.addEventListener("click", () => {
      schedulesModal.classList.add("active");
      fetchSchedules();
    });
  }

  function closeSchedulesModal() {
    if (schedulesModal) schedulesModal.classList.remove("active");
  }

  if (closeSchedulesModalX) closeSchedulesModalX.addEventListener("click", closeSchedulesModal);
  if (closeSchedulesModalBtn) closeSchedulesModalBtn.addEventListener("click", closeSchedulesModal);
  if (schedulesModal) {
    schedulesModal.addEventListener("click", (e) => {
      if (e.target === schedulesModal) closeSchedulesModal();
    });
  }

  // Cron Presets
  const presetCronDaily = document.getElementById("preset-cron-daily");
  if (presetCronDaily && schedCron) {
    presetCronDaily.addEventListener("click", () => {
      schedCron.value = "0 8 * * *";
    });
  }
  const presetCronHourly = document.getElementById("preset-cron-hourly");
  if (presetCronHourly && schedCron) {
    presetCronHourly.addEventListener("click", () => {
      schedCron.value = "0 * * * *";
    });
  }
  const presetCronWeekly = document.getElementById("preset-cron-weekly");
  if (presetCronWeekly && schedCron) {
    presetCronWeekly.addEventListener("click", () => {
      schedCron.value = "0 0 * * 0";
    });
  }

  // Schedule Form Submit
  if (scheduleForm) {
    scheduleForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = schedName ? schedName.value.trim() : "";
      const cronExpr = schedCron ? schedCron.value.trim() : "";
      const query = schedQuery ? schedQuery.value.trim() : "";
      const enabled = schedEnabled ? schedEnabled.checked : true;

      if (!name || !cronExpr || !query) {
        showToast("Please fill in Job Name, Cron Expression, and Prompt Query", "error");
        return;
      }

      try {
        const res = await fetch("/api/schedules", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            cron_expression: cronExpr,
            query,
            enabled,
          }),
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => null);
          throw new Error((errData && errData.detail) || `HTTP ${res.status}`);
        }

        if (schedName) schedName.value = "";
        if (schedCron) schedCron.value = "";
        if (schedQuery) schedQuery.value = "";

        showToast(`Schedule '${name}' created!`);
        fetchSchedules();
      } catch (err) {
        showToast(`Failed to create schedule: ${err.message}`, "error");
      }
    });
  }

  // ── Closed-Loop Skill Distillation (Hermes Self-Learning) ─────────
  const distillSolutionBtn = document.getElementById("distill-solution-btn");
  if (distillSolutionBtn) {
    distillSolutionBtn.addEventListener("click", async () => {
      distillSolutionBtn.disabled = true;
      const originalHtml = distillSolutionBtn.innerHTML;
      distillSolutionBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;">
          <circle cx="12" cy="12" r="10" stroke-dasharray="30" stroke-dashoffset="10"/>
        </svg>
        <span>Distilling Tool...</span>
      `;

      try {
        let skillData = null;
        if (currentWorkflowId) {
          const res = await fetch(`/api/workflows/${currentWorkflowId}/distill-skill`, {
            method: "POST",
          });
          if (res.ok) {
            skillData = await res.json();
          } else {
            const errData = await res.json().catch(() => null);
            console.warn("Distill endpoint error, falling back to generate:", errData);
          }
        }

        if (!skillData) {
          // Fallback to skill generation using prompt input & solution text
          const query = promptInput ? promptInput.value.trim() : "Automated Workflow";
          const solText = solutionBody ? solutionBody.innerText : "";
          const res = await fetch("/api/skills/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              description: `Synthesize a reusable tool from this verified solution for: ${query}. Solution summary: ${solText.slice(0, 300)}`,
              suggested_name: query.toLowerCase().replace(/[^a-z0-9]/g, "_").slice(0, 30),
            }),
          });
          if (res.ok) {
            skillData = await res.json();
          } else {
            throw new Error("Skill distillation service unavailable");
          }
        }

        currentGeneratedSkill = skillData;

        // Open Agents Studio and switch to Skill Builder tab
        if (agentsModal) agentsModal.classList.add("active");
        if (tabBtnSkillBuilder) switchAgentStudioTab(tabBtnSkillBuilder);

        if (skillBuilderDesc) skillBuilderDesc.value = skillData.explanation || "";
        if (skillBuilderName) skillBuilderName.value = skillData.tool_name || "";
        if (skillPreviewSection) skillPreviewSection.style.display = "block";
        if (skillPreviewTitle) skillPreviewTitle.textContent = `Tool: ${skillData.tool_name}`;
        if (skillPreviewRisk) {
          skillPreviewRisk.textContent = (skillData.risk_level || "medium").toUpperCase();
          skillPreviewRisk.className = `risk-badge risk-${(skillData.risk_level || "medium").toLowerCase()}`;
        }
        if (skillPreviewSkills) {
          skillPreviewSkills.innerHTML = (skillData.skill_names || [])
            .map((s) => `<span class="skill-tag">${s}</span>`)
            .join("");
        }
        if (skillPreviewExplanation) skillPreviewExplanation.textContent = skillData.explanation || "";
        if (skillPreviewCode) skillPreviewCode.value = skillData.tool_code || "";
        if (skillRegisterStatus) skillRegisterStatus.style.display = "none";

        showToast("Workflow solution distilled into reusable Python tool! Click 'Register & Persist' to save.", "success");
      } catch (err) {
        showToast(`Distillation failed: ${err.message}`, "error");
      } finally {
        distillSolutionBtn.disabled = false;
        distillSolutionBtn.innerHTML = originalHtml;
      }
    });
  }
});


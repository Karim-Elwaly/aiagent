/**
 * AgentHub SVG DAG Renderer — 2026 Pro Edition
 * Renders dynamic TaskDAG graphs with topological auto-layout,
 * smooth cubic bezier connectors, glowing status indicators, and clean text wrapping.
 */

class DAGRenderer {
  constructor(svgElementId, onNodeClick = null) {
    this.svg = document.getElementById(svgElementId);
    this.onNodeClick = onNodeClick;
    this.dag = null;
    this.nodeMap = new Map(); // id -> { task, x, y, width, height, status }
    this.statusMap = new Map(); // id -> status ("pending", "running", "completed", "failed", "approval")
    this.nodeWidth = 230;
    this.nodeHeight = 92;
    this.colSpacing = 90;
    this.rowSpacing = 28;
  }

  render(dag) {
    this.dag = dag;
    this.svg.innerHTML = ""; // Clear canvas
    this.nodeMap.clear();

    const emptyEl = document.getElementById("dag-empty");
    if (!dag || !dag.tasks || dag.tasks.length === 0) {
      if (emptyEl) emptyEl.style.display = "flex";
      return;
    }
    if (emptyEl) emptyEl.style.display = "none";

    // 1. Assign topological levels to tasks
    const levels = this._computeLevels(dag.tasks);

    // 2. Compute coordinates for each node
    const maxRows = Math.max(...levels.map((lvl) => lvl.length), 1);
    const totalWidth = levels.length * (this.nodeWidth + this.colSpacing) + 80;
    const totalHeight = maxRows * (this.nodeHeight + this.rowSpacing) + 70;

    this.svg.setAttribute("viewBox", `0 0 ${Math.max(totalWidth, 720)} ${Math.max(totalHeight, 320)}`);

    levels.forEach((tasksInLevel, colIdx) => {
      const colX = 36 + colIdx * (this.nodeWidth + this.colSpacing);
      const totalColHeight = tasksInLevel.length * (this.nodeHeight + this.rowSpacing) - this.rowSpacing;
      const startY = Math.max(30, (totalHeight - totalColHeight) / 2);

      tasksInLevel.forEach((task, rowIdx) => {
        const rowY = startY + rowIdx * (this.nodeHeight + this.rowSpacing);
        const status = this.statusMap.get(task.id) || "pending";

        this.nodeMap.set(task.id, {
          task,
          x: colX,
          y: rowY,
          width: this.nodeWidth,
          height: this.nodeHeight,
          status,
        });
      });
    });

    // 3. Draw connecting edges (smooth bezier curves)
    const edgeGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    edgeGroup.setAttribute("class", "dag-edges");
    this.svg.appendChild(edgeGroup);

    dag.tasks.forEach((task) => {
      const targetNode = this.nodeMap.get(task.id);
      if (!targetNode) return;

      (task.dependencies || []).forEach((depId) => {
        const sourceNode = this.nodeMap.get(depId);
        if (!sourceNode) return;

        const path = this._createEdgePath(sourceNode, targetNode);
        edgeGroup.appendChild(path);
      });
    });

    // 4. Draw nodes
    const nodeGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    nodeGroup.setAttribute("class", "dag-nodes");
    this.svg.appendChild(nodeGroup);

    this.nodeMap.forEach((node) => {
      const nodeEl = this._createNodeElement(node);
      nodeGroup.appendChild(nodeEl);
    });
  }

  updateNodeStatus(taskId, status) {
    this.statusMap.set(taskId, status);
    const nodeData = this.nodeMap.get(taskId);
    if (!nodeData) return;

    nodeData.status = status;
    const box = document.getElementById(`node-box-${taskId}`);
    const badge = document.getElementById(`node-status-${taskId}`);
    const statusDot = document.getElementById(`node-dot-${taskId}`);

    if (box) {
      box.setAttribute("class", `node-box status-${status}`);
    }
    if (badge) {
      const labelMap = {
        pending: "PENDING",
        running: "RUNNING",
        completed: "DONE",
        failed: "FAILED",
        approval: "APPROVAL",
      };
      badge.textContent = labelMap[status] || status.toUpperCase();
      badge.setAttribute("class", `node-badge badge-${status}`);
    }
    if (statusDot) {
      statusDot.setAttribute("class", `node-status-dot dot-${status}`);
    }

    // Update active edge animation if running
    const edges = this.svg.querySelectorAll(`[data-target="${taskId}"]`);
    edges.forEach((edge) => {
      if (status === "running") {
        edge.classList.add("active");
      } else {
        edge.classList.remove("active");
      }
    });
  }

  _computeLevels(tasks) {
    const taskMap = new Map(tasks.map((t) => [t.id, t]));
    const levelMap = new Map();

    const getLevel = (taskId, visited = new Set()) => {
      if (levelMap.has(taskId)) return levelMap.get(taskId);
      if (visited.has(taskId)) return 0; // Prevent cycle loops
      visited.add(taskId);

      const task = taskMap.get(taskId);
      if (!task || !task.dependencies || task.dependencies.length === 0) {
        levelMap.set(taskId, 0);
        return 0;
      }

      let maxDepLevel = 0;
      for (const depId of task.dependencies) {
        maxDepLevel = Math.max(maxDepLevel, getLevel(depId, new Set(visited)) + 1);
      }

      levelMap.set(taskId, maxDepLevel);
      return maxDepLevel;
    };

    tasks.forEach((t) => getLevel(t.id));

    const maxLevel = Math.max(...Array.from(levelMap.values()), 0);
    const levels = Array.from({ length: maxLevel + 1 }, () => []);

    tasks.forEach((t) => {
      const lvl = levelMap.get(t.id) || 0;
      levels[lvl].push(t);
    });

    return levels;
  }

  _createEdgePath(source, target) {
    const x1 = source.x + source.width;
    const y1 = source.y + source.height / 2;
    const x2 = target.x;
    const y2 = target.y + target.height / 2;

    const dx = Math.abs(x2 - x1) * 0.52;
    const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("class", "edge-path");
    path.setAttribute("data-source", source.task.id);
    path.setAttribute("data-target", target.task.id);
    return path;
  }

  _createNodeElement(node) {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const isEditable = node.status === "pending";
    g.setAttribute("class", `dag-node ${isEditable ? "node-editable" : ""}`);
    g.setAttribute("transform", `translate(${node.x}, ${node.y})`);

    // Rich Native Tooltip for complete task details
    const titleEl = document.createElementNS("http://www.w3.org/2000/svg", "title");
    const skillList = (node.task.required_skills || []).join(", ") || "General";
    titleEl.textContent = `${node.task.name || node.task.id} (${node.task.id.toUpperCase()})\n` +
      `Risk: ${(node.task.risk_level || 'low').toUpperCase()} | Status: ${node.status.toUpperCase()}\n` +
      `Skills: ${skillList}\n` +
      `Description: ${node.task.description || 'No description provided'}` +
      (isEditable ? "\n\n👉 Click to edit parameters, risk level, or guidance before execution" : "");
    g.appendChild(titleEl);

    // Box background
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("id", `node-box-${node.task.id}`);
    rect.setAttribute("class", `node-box status-${node.status}`);
    rect.setAttribute("width", node.width);
    rect.setAttribute("height", node.height);
    rect.setAttribute("rx", "12");
    g.appendChild(rect);

    // Subtle header separator line
    const sep = document.createElementNS("http://www.w3.org/2000/svg", "line");
    sep.setAttribute("x1", "12");
    sep.setAttribute("y1", "26");
    sep.setAttribute("x2", String(node.width - 12));
    sep.setAttribute("y2", "26");
    sep.setAttribute("stroke", "rgba(255, 255, 255, 0.07)");
    sep.setAttribute("stroke-width", "1");
    g.appendChild(sep);

    // Task ID Pill Background
    const idPill = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    idPill.setAttribute("x", "12");
    idPill.setAttribute("y", "7");
    idPill.setAttribute("width", "34");
    idPill.setAttribute("height", "15");
    idPill.setAttribute("rx", "3");
    idPill.setAttribute("fill", "rgba(99, 102, 241, 0.2)");
    idPill.setAttribute("stroke", "rgba(99, 102, 241, 0.4)");
    idPill.setAttribute("stroke-width", "0.8");
    g.appendChild(idPill);

    // Task ID Text
    const textId = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textId.setAttribute("x", "29");
    textId.setAttribute("y", "18");
    textId.setAttribute("text-anchor", "middle");
    textId.setAttribute("fill", "#a5b4fc");
    textId.setAttribute("font-family", "JetBrains Mono");
    textId.setAttribute("font-size", "9.5");
    textId.setAttribute("font-weight", "700");
    textId.textContent = node.task.id.toUpperCase();
    g.appendChild(textId);

    // Custom Parameter Override Pill (in header)
    const isCustomized = node.task.is_customized ||
      (node.task.parameters && Object.keys(node.task.parameters).length > 0) ||
      (node.task.description && node.task.description.includes("[OPERATOR GUIDANCE]")) ||
      node.task.operator_guidance;

    if (isCustomized) {
      const customPill = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      customPill.setAttribute("x", "50");
      customPill.setAttribute("y", "7");
      customPill.setAttribute("width", "52");
      customPill.setAttribute("height", "15");
      customPill.setAttribute("rx", "3");
      customPill.setAttribute("fill", "rgba(192, 132, 252, 0.2)");
      customPill.setAttribute("stroke", "rgba(192, 132, 252, 0.5)");
      customPill.setAttribute("stroke-width", "0.8");
      g.appendChild(customPill);

      const customText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      customText.setAttribute("x", "76");
      customText.setAttribute("y", "18");
      customText.setAttribute("text-anchor", "middle");
      customText.setAttribute("fill", "#d8b4fe");
      customText.setAttribute("font-family", "JetBrains Mono");
      customText.setAttribute("font-size", "8");
      customText.setAttribute("font-weight", "700");
      customText.textContent = "⚡CUSTOM";
      g.appendChild(customText);
    }

    // Risk Level Badge (Right side of header)
    const riskLevel = (node.task.risk_level || "low").toLowerCase();
    const riskColors = {
      critical: { bg: "rgba(239, 68, 68, 0.2)", stroke: "rgba(239, 68, 68, 0.5)", text: "#f87171" },
      high: { bg: "rgba(245, 158, 11, 0.2)", stroke: "rgba(245, 158, 11, 0.5)", text: "#fbbf24" },
      medium: { bg: "rgba(59, 130, 246, 0.15)", stroke: "rgba(59, 130, 246, 0.4)", text: "#60a5fa" },
      low: { bg: "rgba(16, 185, 129, 0.15)", stroke: "rgba(16, 185, 129, 0.4)", text: "#34d399" },
    };
    const rConfig = riskColors[riskLevel] || riskColors.low;

    const riskPill = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    riskPill.setAttribute("x", String(node.width - 56));
    riskPill.setAttribute("y", "7");
    riskPill.setAttribute("width", "44");
    riskPill.setAttribute("height", "15");
    riskPill.setAttribute("rx", "3");
    riskPill.setAttribute("fill", rConfig.bg);
    riskPill.setAttribute("stroke", rConfig.stroke);
    riskPill.setAttribute("stroke-width", "0.8");
    g.appendChild(riskPill);

    const textRisk = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textRisk.setAttribute("x", String(node.width - 34));
    textRisk.setAttribute("y", "18");
    textRisk.setAttribute("text-anchor", "middle");
    textRisk.setAttribute("fill", rConfig.text);
    textRisk.setAttribute("font-family", "JetBrains Mono");
    textRisk.setAttribute("font-size", "8.5");
    textRisk.setAttribute("font-weight", "700");
    textRisk.textContent = riskLevel.toUpperCase();
    g.appendChild(textRisk);

    // Multi-line Task Name (Intelligent splitting so title fits perfectly)
    const rawName = node.task.name || "Task";
    const nameLines = this._wrapText(rawName, 26, 2);

    if (nameLines.length === 1) {
      const textName = document.createElementNS("http://www.w3.org/2000/svg", "text");
      textName.setAttribute("x", "12");
      textName.setAttribute("y", "44");
      textName.setAttribute("fill", "#f1f5f9");
      textName.setAttribute("font-family", "Outfit, -apple-system, sans-serif");
      textName.setAttribute("font-size", "12.5");
      textName.setAttribute("font-weight", "600");
      textName.textContent = nameLines[0];
      g.appendChild(textName);
    } else {
      const textName1 = document.createElementNS("http://www.w3.org/2000/svg", "text");
      textName1.setAttribute("x", "12");
      textName1.setAttribute("y", "40");
      textName1.setAttribute("fill", "#f1f5f9");
      textName1.setAttribute("font-family", "Outfit, -apple-system, sans-serif");
      textName1.setAttribute("font-size", "12");
      textName1.setAttribute("font-weight", "600");
      textName1.textContent = nameLines[0];
      g.appendChild(textName1);

      const textName2 = document.createElementNS("http://www.w3.org/2000/svg", "text");
      textName2.setAttribute("x", "12");
      textName2.setAttribute("y", "54");
      textName2.setAttribute("fill", "#cbd5e1");
      textName2.setAttribute("font-family", "Outfit, -apple-system, sans-serif");
      textName2.setAttribute("font-size", "11");
      textName2.setAttribute("font-weight", "500");
      textName2.textContent = nameLines[1];
      g.appendChild(textName2);
    }

    // Skills preview subtitle (truncated cleanly with ellipsis)
    const textSkill = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textSkill.setAttribute("x", "12");
    textSkill.setAttribute("y", "72");
    textSkill.setAttribute("fill", "#64748b");
    textSkill.setAttribute("font-family", "JetBrains Mono");
    textSkill.setAttribute("font-size", "9");
    const skillStr = skillList.length > 24 ? skillList.substring(0, 22) + "…" : skillList;
    textSkill.textContent = `⚙ ${skillStr}`;
    g.appendChild(textSkill);

    // Status Badge Pill (Bottom right)
    const statusBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    statusBg.setAttribute("x", String(node.width - 68));
    statusBg.setAttribute("y", "64");
    statusBg.setAttribute("width", "56");
    statusBg.setAttribute("height", "18");
    statusBg.setAttribute("rx", "9");
    statusBg.setAttribute("fill", "rgba(255, 255, 255, 0.04)");
    statusBg.setAttribute("stroke", "rgba(255, 255, 255, 0.1)");
    statusBg.setAttribute("stroke-width", "0.8");
    g.appendChild(statusBg);

    // Status Dot indicator
    const statusDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    statusDot.setAttribute("id", `node-dot-${node.task.id}`);
    statusDot.setAttribute("class", `node-status-dot dot-${node.status}`);
    statusDot.setAttribute("cx", String(node.width - 58));
    statusDot.setAttribute("cy", "73");
    statusDot.setAttribute("r", "3");
    g.appendChild(statusDot);

    // Status text
    const statusText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    statusText.setAttribute("id", `node-status-${node.task.id}`);
    statusText.setAttribute("class", `node-badge badge-${node.status}`);
    statusText.setAttribute("x", String(node.width - 40));
    statusText.setAttribute("y", "76");
    statusText.setAttribute("text-anchor", "middle");
    statusText.setAttribute("font-family", "JetBrains Mono");
    statusText.setAttribute("font-size", "8.5");
    statusText.setAttribute("font-weight", "700");
    const labelMap = {
      pending: "PENDING",
      running: "RUNNING",
      completed: "DONE",
      failed: "FAILED",
      approval: "APPROVAL",
    };
    statusText.textContent = labelMap[node.status] || node.status.toUpperCase();
    g.appendChild(statusText);

    // Click handler
    g.addEventListener("click", () => {
      if (this.onNodeClick) {
        this.onNodeClick(node.task, node.status);
      }
    });

    return g;
  }

  _wrapText(text, maxCharsPerLine = 26, maxLines = 2) {
    if (!text) return ["Task"];
    if (text.length <= maxCharsPerLine) return [text];

    const words = text.split(" ");
    const lines = [];
    let currentLine = "";

    for (const word of words) {
      if ((currentLine + " " + word).trim().length <= maxCharsPerLine) {
        currentLine = (currentLine + " " + word).trim();
      } else {
        if (currentLine) lines.push(currentLine);
        currentLine = word;
        if (lines.length >= maxLines - 1) break;
      }
    }

    if (currentLine) {
      if (lines.length < maxLines) {
        lines.push(currentLine);
      } else {
        lines[lines.length - 1] += " " + currentLine;
      }
    }

    // Ellipsize the final line if it exceeds maxChars
    if (lines.length >= maxLines && lines[maxLines - 1].length > maxCharsPerLine) {
      lines[maxLines - 1] = lines[maxLines - 1].substring(0, maxCharsPerLine - 2) + "…";
    }

    return lines;
  }

  reset() {
    this.dag = null;
    this.svg.innerHTML = "";
    this.nodeMap.clear();
    this.statusMap.clear();
    const emptyEl = document.getElementById("dag-empty");
    if (emptyEl) emptyEl.style.display = "flex";
  }
}

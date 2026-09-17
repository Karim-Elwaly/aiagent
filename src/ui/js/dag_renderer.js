/**
 * UAOS SVG DAG Renderer
 * Renders dynamic TaskDAG graphs with topological auto-layout,
 * smooth cubic bezier connectors, and animated status particles.
 */

class DAGRenderer {
  constructor(svgElementId, onNodeClick = null) {
    this.svg = document.getElementById(svgElementId);
    this.onNodeClick = onNodeClick;
    this.dag = null;
    this.nodeMap = new Map(); // id -> { task, x, y, width, height, status }
    this.statusMap = new Map(); // id -> status ("pending", "running", "completed", "failed", "approval")
    this.nodeWidth = 190;
    this.nodeHeight = 76;
    this.colSpacing = 110;
    this.rowSpacing = 30;
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
    const maxRows = Math.max(...levels.map((lvl) => lvl.length));
    const totalWidth = levels.length * (this.nodeWidth + this.colSpacing) + 60;
    const totalHeight = maxRows * (this.nodeHeight + this.rowSpacing) + 60;

    this.svg.setAttribute("viewBox", `0 0 ${Math.max(totalWidth, 700)} ${Math.max(totalHeight, 360)}`);

    levels.forEach((tasksInLevel, colIdx) => {
      const colX = 40 + colIdx * (this.nodeWidth + this.colSpacing);
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

    // 3. Draw connecting edges (bezier curves)
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

    if (box) {
      box.setAttribute("class", `node-box status-${status}`);
    }
    if (badge) {
      badge.textContent = status.toUpperCase();
      badge.setAttribute("class", `node-badge badge-${status}`);
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

    const dx = Math.abs(x2 - x1) * 0.55;
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
    g.setAttribute("class", "dag-node");
    g.setAttribute("transform", `translate(${node.x}, ${node.y})`);

    // Box background
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("id", `node-box-${node.task.id}`);
    rect.setAttribute("class", `node-box status-${node.status}`);
    rect.setAttribute("width", node.width);
    rect.setAttribute("height", node.height);
    g.appendChild(rect);

    // Header text: ID and Name
    const textId = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textId.setAttribute("x", "14");
    textId.setAttribute("y", "24");
    textId.setAttribute("fill", "#06b6d4");
    textId.setAttribute("font-family", "JetBrains Mono");
    textId.setAttribute("font-size", "11");
    textId.setAttribute("font-weight", "bold");
    textId.textContent = node.task.id.toUpperCase();
    g.appendChild(textId);

    const textName = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textName.setAttribute("x", "44");
    textName.setAttribute("y", "24");
    textName.setAttribute("fill", "#f8fafc");
    textName.setAttribute("font-family", "Outfit");
    textName.setAttribute("font-size", "13");
    textName.setAttribute("font-weight", "600");
    const nameStr = node.task.name || "Task";
    textName.textContent = nameStr.length > 18 ? nameStr.substring(0, 16) + "..." : nameStr;
    g.appendChild(textName);

    // Skill subtitle
    const textSkill = document.createElementNS("http://www.w3.org/2000/svg", "text");
    textSkill.setAttribute("x", "14");
    textSkill.setAttribute("y", "46");
    textSkill.setAttribute("fill", "#94a3b8");
    textSkill.setAttribute("font-family", "Outfit");
    textSkill.setAttribute("font-size", "11");
    const skills = (node.task.required_skills || []).join(", ") || "General";
    textSkill.textContent = skills.length > 25 ? skills.substring(0, 23) + "..." : skills;
    g.appendChild(textSkill);

    // Status pill
    const statusBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    statusBg.setAttribute("x", "14");
    statusBg.setAttribute("y", "54");
    statusBg.setAttribute("width", "72");
    statusBg.setAttribute("height", "14");
    statusBg.setAttribute("rx", "4");
    statusBg.setAttribute("fill", "rgba(255, 255, 255, 0.05)");
    g.appendChild(statusBg);

    const statusText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    statusText.setAttribute("id", `node-status-${node.task.id}`);
    statusText.setAttribute("x", "18");
    statusText.setAttribute("y", "64");
    statusText.setAttribute("fill", "#cbd5e1");
    statusText.setAttribute("font-family", "JetBrains Mono");
    statusText.setAttribute("font-size", "9");
    statusText.setAttribute("font-weight", "bold");
    statusText.textContent = node.status.toUpperCase();
    g.appendChild(statusText);

    // Click handler
    g.addEventListener("click", () => {
      if (this.onNodeClick) {
        this.onNodeClick(node.task, node.status);
      }
    });

    return g;
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
